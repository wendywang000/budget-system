"""報表:多部門彙總與預算 vs 實際差異分析。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_department_ids, get_current_user
from ..models import Actual, BudgetEntry, BudgetVersion, GrantModule, User
from ..schemas import (
    SummaryResponse,
    SummaryRow,
    VarianceResponse,
    VarianceRow,
    VersionOut,
)
from ..services.tree import (
    has_children_map,
    load_accounts,
    load_departments,
    ordered_tree,
    rollup,
)

router = APIRouter(prefix="/reports", tags=["報表"])

MONTHS = tuple(range(1, 13))


# --------------------------------------------------------------------------- #
# 共用工具
# --------------------------------------------------------------------------- #
def get_version(db: Session, version_id: int) -> BudgetVersion:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算版本不存在")
    return version


def department_scope(db: Session, user: User, department_id: int | None) -> set[int] | None:
    """回傳報表要納入的部門 id;None 表示全部。

    可查詢的部門 = budget 模組(自己填報的部門)與 report 模組(額外被授予的報表查詢部門)的聯集。
    """
    from ..services.tree import descendant_department_ids

    budget_scope = accessible_department_ids(db, user, GrantModule.budget)
    report_scope = accessible_department_ids(db, user, GrantModule.report)
    if budget_scope is None or report_scope is None:
        allowed = None
    else:
        allowed = budget_scope | report_scope
    if department_id is None:
        return allowed
    subtree = descendant_department_ids(db, department_id)
    if allowed is not None and not subtree & allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該部門的資料")
    return subtree if allowed is None else subtree & allowed


def budget_by_account(db: Session, version_id: int, scope: set[int] | None) -> dict[int, dict[int, float]]:
    values: dict[int, dict[int, float]] = {}
    for entry in db.scalars(select(BudgetEntry).where(BudgetEntry.version_id == version_id)):
        if scope is not None and entry.department_id not in scope:
            continue
        if entry.month not in MONTHS:
            continue
        bucket = values.setdefault(entry.account_id, {})
        bucket[entry.month] = bucket.get(entry.month, 0.0) + float(entry.amount or 0)
    return values


def budget_by_department(db: Session, version_id: int, scope: set[int] | None) -> dict[int, dict[int, float]]:
    values: dict[int, dict[int, float]] = {}
    for entry in db.scalars(select(BudgetEntry).where(BudgetEntry.version_id == version_id)):
        if scope is not None and entry.department_id not in scope:
            continue
        if entry.month not in MONTHS:
            continue
        bucket = values.setdefault(entry.department_id, {})
        bucket[entry.month] = bucket.get(entry.month, 0.0) + float(entry.amount or 0)
    return values


def actual_by_account(db: Session, fiscal_year: int, scope: set[int] | None) -> dict[int, dict[int, float]]:
    values: dict[int, dict[int, float]] = {}
    for row in db.scalars(select(Actual).where(Actual.fiscal_year == fiscal_year)):
        if scope is not None and row.department_id not in scope:
            continue
        if row.month not in MONTHS:
            continue
        bucket = values.setdefault(row.account_id, {})
        bucket[row.month] = bucket.get(row.month, 0.0) + float(row.amount or 0)
    return values


def actual_by_department(db: Session, fiscal_year: int, scope: set[int] | None) -> dict[int, dict[int, float]]:
    values: dict[int, dict[int, float]] = {}
    for row in db.scalars(select(Actual).where(Actual.fiscal_year == fiscal_year)):
        if scope is not None and row.department_id not in scope:
            continue
        if row.month not in MONTHS:
            continue
        bucket = values.setdefault(row.department_id, {})
        bucket[row.month] = bucket.get(row.month, 0.0) + float(row.amount or 0)
    return values


def _ytd(months: dict[int, float], through: int) -> float:
    return round(sum(v for m, v in months.items() if m <= through), 2)


# --------------------------------------------------------------------------- #
# 彙總表
# --------------------------------------------------------------------------- #
@router.get("/summary", response_model=SummaryResponse, summary="預算彙總(依科目或依部門)")
def summary(
    version_id: int,
    group_by: str = Query("account", pattern="^(account|department)$"),
    department_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryResponse:
    version = get_version(db, version_id)
    scope = department_scope(db, user, department_id)

    if group_by == "account":
        nodes = load_accounts(db)
        own = budget_by_account(db, version_id, scope)
        visible = {node.id for node in nodes}
    else:
        nodes = load_departments(db)
        own = budget_by_department(db, version_id, scope)
        visible = {node.id for node in nodes} if scope is None else {n.id for n in nodes if n.id in scope}

    child_flags = has_children_map(nodes)
    totals = rollup(nodes, own)

    rows: list[SummaryRow] = []
    month_totals = {m: 0.0 for m in MONTHS}

    for node, level in ordered_tree(nodes):
        if node.id not in visible:
            continue
        is_group = child_flags.get(node.id, False)
        source = totals.get(node.id, {}) if is_group else own.get(node.id, {})
        months = {m: round(float(source.get(m, 0.0)), 2) for m in MONTHS}
        row_total = round(sum(months.values()), 2)
        if row_total == 0 and is_group and all(v == 0 for v in months.values()):
            # 完全沒有數字的群組仍保留,方便對照科目表結構
            pass
        rows.append(
            SummaryRow(
                key=f"{group_by}-{node.id}",
                code=node.code,
                name=node.name,
                level=level,
                category=getattr(node, "category", None).value if hasattr(node, "category") else None,
                months=months,
                total=row_total,
                is_group=is_group,
            )
        )
        if not is_group:
            for month in MONTHS:
                month_totals[month] = round(month_totals[month] + months[month], 2)

    return SummaryResponse(
        version=VersionOut.model_validate(version),
        group_by=group_by,
        rows=rows,
        month_totals=month_totals,
        grand_total=round(sum(month_totals.values()), 2),
    )


# --------------------------------------------------------------------------- #
# 差異分析
# --------------------------------------------------------------------------- #
@router.get("/variance", response_model=VarianceResponse, summary="預算 vs 實際差異分析")
def variance(
    version_id: int,
    through_month: int = Query(12, ge=1, le=12, description="累計至第幾個月"),
    group_by: str = Query("account", pattern="^(account|department)$"),
    department_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VarianceResponse:
    version = get_version(db, version_id)
    scope = department_scope(db, user, department_id)
    year = version.fiscal_year

    if group_by == "account":
        nodes = load_accounts(db)
        own_budget = budget_by_account(db, version_id, scope)
        own_actual = actual_by_account(db, year, scope)
        visible = {node.id for node in nodes}
    else:
        nodes = load_departments(db)
        own_budget = budget_by_department(db, version_id, scope)
        own_actual = actual_by_department(db, year, scope)
        visible = {node.id for node in nodes} if scope is None else {n.id for n in nodes if n.id in scope}

    child_flags = has_children_map(nodes)
    budget_totals = rollup(nodes, own_budget)
    actual_totals = rollup(nodes, own_actual)

    rows: list[VarianceRow] = []
    agg = {"budget": 0.0, "actual": 0.0, "budget_ytd": 0.0, "actual_ytd": 0.0}

    for node, level in ordered_tree(nodes):
        if node.id not in visible:
            continue
        is_group = child_flags.get(node.id, False)
        b_months = (budget_totals if is_group else own_budget).get(node.id, {})
        a_months = (actual_totals if is_group else own_actual).get(node.id, {})

        budget_full = round(sum(b_months.values()), 2)
        actual_full = round(sum(a_months.values()), 2)
        budget_ytd = _ytd(b_months, through_month)
        actual_ytd = _ytd(a_months, through_month)

        rows.append(
            VarianceRow(
                key=f"{group_by}-{node.id}",
                code=node.code,
                name=node.name,
                level=level,
                category=getattr(node, "category", None).value if hasattr(node, "category") else None,
                is_group=is_group,
                budget=budget_full,
                actual=actual_full,
                variance=round(actual_full - budget_full, 2),
                achievement=round(actual_ytd / budget_ytd * 100, 2) if budget_ytd else None,
                budget_ytd=budget_ytd,
                actual_ytd=actual_ytd,
                variance_ytd=round(actual_ytd - budget_ytd, 2),
            )
        )
        if not is_group:
            agg["budget"] += budget_full
            agg["actual"] += actual_full
            agg["budget_ytd"] += budget_ytd
            agg["actual_ytd"] += actual_ytd

    totals = VarianceRow(
        key="total",
        code="",
        name="合計",
        level=0,
        is_group=True,
        budget=round(agg["budget"], 2),
        actual=round(agg["actual"], 2),
        variance=round(agg["actual"] - agg["budget"], 2),
        achievement=round(agg["actual_ytd"] / agg["budget_ytd"] * 100, 2) if agg["budget_ytd"] else None,
        budget_ytd=round(agg["budget_ytd"], 2),
        actual_ytd=round(agg["actual_ytd"], 2),
        variance_ytd=round(agg["actual_ytd"] - agg["budget_ytd"], 2),
    )

    return VarianceResponse(
        fiscal_year=year,
        version=VersionOut.model_validate(version),
        through_month=through_month,
        group_by=group_by,
        rows=rows,
        totals=totals,
    )
