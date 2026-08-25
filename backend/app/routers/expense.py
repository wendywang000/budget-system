"""費用預算:每種「收集格式」有自己的欄位組合,依部門功能別(銷/管/研/製)對應到會計科目。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    accessible_department_ids,
    accessible_expense_format_ids,
    assert_expense_format_access,
    get_current_user,
    require_admin,
)
from ..models import (
    Account,
    BudgetEntry,
    BudgetVersion,
    Department,
    ExpenseEntry,
    ExpenseFormat,
    ExpenseFormatAccountMap,
    ExpenseFormatColumn,
    ExpenseFunction,
    GrantModule,
    Submission,
    User,
    UserRole,
)
from ..schemas import (
    DepartmentOut,
    ExpenseCellIn,
    ExpenseFormatAccountMapOut,
    ExpenseFormatCreate,
    ExpenseFormatOut,
    ExpenseFormatUpdate,
    ExpenseGridCellOut,
    ExpenseGridResponse,
    ExpenseSaveRequest,
    ExpenseSyncResult,
    VersionOut,
)
from ..services.workflow import is_editable

router = APIRouter(tags=["費用預算"])

MONTHS = tuple(range(1, 13))


def _format_out(fmt: ExpenseFormat) -> ExpenseFormatOut:
    return ExpenseFormatOut(
        id=fmt.id,
        code=fmt.code,
        name=fmt.name,
        sort_order=fmt.sort_order,
        is_active=fmt.is_active,
        columns=[
            {"id": c.id, "key": c.key, "label": c.label, "sort_order": c.sort_order}
            for c in sorted(fmt.columns, key=lambda c: c.sort_order)
        ],
        account_maps=[
            ExpenseFormatAccountMapOut(
                function=m.function,
                account_id=m.account_id,
                account_code=m.account.code if m.account else None,
                account_name=m.account.name if m.account else None,
            )
            for m in fmt.account_maps
        ],
    )


# --------------------------------------------------------------------------- #
# 費用格式主檔(財務管理者維護)
# --------------------------------------------------------------------------- #
@router.get("/expense-formats", response_model=list[ExpenseFormatOut], summary="費用收集格式清單")
def list_formats(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExpenseFormatOut]:
    stmt = select(ExpenseFormat).order_by(ExpenseFormat.sort_order, ExpenseFormat.code)
    if active_only:
        stmt = stmt.where(ExpenseFormat.is_active.is_(True))
    return [_format_out(f) for f in db.scalars(stmt)]


@router.post("/expense-formats", response_model=ExpenseFormatOut, status_code=201, summary="新增費用收集格式")
def create_format(
    payload: ExpenseFormatCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExpenseFormatOut:
    if db.scalar(select(ExpenseFormat).where(ExpenseFormat.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "費用格式代號已存在")
    fmt = ExpenseFormat(code=payload.code, name=payload.name, sort_order=payload.sort_order)
    db.add(fmt)
    db.flush()
    for col in payload.columns:
        db.add(ExpenseFormatColumn(format_id=fmt.id, key=col.key, label=col.label, sort_order=col.sort_order))
    for m in payload.account_maps:
        if db.get(Account, m.account_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"科目 {m.account_id} 不存在")
        db.add(ExpenseFormatAccountMap(format_id=fmt.id, function=m.function, account_id=m.account_id))
    db.commit()
    db.refresh(fmt)
    return _format_out(fmt)


@router.patch("/expense-formats/{format_id}", response_model=ExpenseFormatOut, summary="修改費用收集格式")
def update_format(
    format_id: int,
    payload: ExpenseFormatUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExpenseFormatOut:
    fmt = db.get(ExpenseFormat, format_id)
    if fmt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")
    data = payload.model_dump(exclude_unset=True, exclude={"columns", "account_maps"})
    if "code" in data and data["code"] != fmt.code:
        if db.scalar(select(ExpenseFormat).where(ExpenseFormat.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "費用格式代號已存在")
    for field, value in data.items():
        setattr(fmt, field, value)

    if payload.columns is not None:
        db.query(ExpenseFormatColumn).filter(ExpenseFormatColumn.format_id == format_id).delete()
        for col in payload.columns:
            db.add(ExpenseFormatColumn(format_id=format_id, key=col.key, label=col.label, sort_order=col.sort_order))
    if payload.account_maps is not None:
        db.query(ExpenseFormatAccountMap).filter(ExpenseFormatAccountMap.format_id == format_id).delete()
        for m in payload.account_maps:
            if db.get(Account, m.account_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"科目 {m.account_id} 不存在")
            db.add(ExpenseFormatAccountMap(format_id=format_id, function=m.function, account_id=m.account_id))

    db.add(fmt)
    db.commit()
    db.refresh(fmt)
    return _format_out(fmt)


@router.delete("/expense-formats/{format_id}", status_code=204, response_model=None, summary="刪除費用收集格式")
def delete_format(
    format_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    fmt = db.get(ExpenseFormat, format_id)
    if fmt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")
    if db.scalar(select(ExpenseEntry.id).where(ExpenseEntry.format_id == format_id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "此格式已有費用預算資料,請改為停用")
    db.delete(fmt)
    db.commit()


# --------------------------------------------------------------------------- #
# 費用預算填報
# --------------------------------------------------------------------------- #
def _get_version(db: Session, version_id: int) -> BudgetVersion:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算版本不存在")
    return version


def _get_submission(db: Session, version_id: int, department_id: int) -> Submission | None:
    return db.scalar(
        select(Submission).where(Submission.version_id == version_id, Submission.department_id == department_id)
    )


def _resolve_account(fmt: ExpenseFormat, function: ExpenseFunction | None) -> ExpenseFormatAccountMap | None:
    if function is None:
        return None
    return next((m for m in fmt.account_maps if m.function == function), None)


@router.get("/expense/formats-for-department", response_model=list[ExpenseFormatOut], summary="我可填報此部門的費用格式清單")
def formats_for_department(
    department_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExpenseFormatOut]:
    formats = db.scalars(
        select(ExpenseFormat).where(ExpenseFormat.is_active.is_(True)).order_by(ExpenseFormat.sort_order)
    ).all()

    if user.role == UserRole.finance_admin:
        return [_format_out(f) for f in formats]

    dept_scope = accessible_department_ids(db, user, GrantModule.expense)
    if dept_scope is not None and department_id in dept_scope:
        return [_format_out(f) for f in formats]  # 整部門授權,所有啟用中的格式都能填

    allowed_format_ids = accessible_expense_format_ids(db, user, department_id)
    if not allowed_format_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該部門的費用預算資料")
    return [_format_out(f) for f in formats if f.id in allowed_format_ids]


@router.get("/expense/grid", response_model=ExpenseGridResponse, summary="取得某部門某格式的費用預算表")
def get_grid(
    version_id: int,
    department_id: int,
    format_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseGridResponse:
    version = _get_version(db, version_id)
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    fmt = db.get(ExpenseFormat, format_id)
    if fmt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")
    assert_expense_format_access(db, user, department_id, format_id)

    entries = db.scalars(
        select(ExpenseEntry).where(
            ExpenseEntry.version_id == version_id,
            ExpenseEntry.department_id == department_id,
            ExpenseEntry.format_id == format_id,
        )
    ).all()
    by_column: dict[str, dict[int, float]] = {}
    for e in entries:
        by_column.setdefault(e.column_key, {})[e.month] = float(e.amount or 0)

    columns = sorted(fmt.columns, key=lambda c: c.sort_order)
    rows: list[ExpenseGridCellOut] = []
    month_totals = {m: 0.0 for m in MONTHS}
    for col in columns:
        months = {m: round(by_column.get(col.key, {}).get(m, 0.0), 2) for m in MONTHS}
        for m in MONTHS:
            month_totals[m] = round(month_totals[m] + months[m], 2)
        rows.append(
            ExpenseGridCellOut(column_key=col.key, column_label=col.label, months=months, total=round(sum(months.values()), 2))
        )

    submission = _get_submission(db, version_id, department_id)
    account_map = _resolve_account(fmt, dept.function)
    return ExpenseGridResponse(
        version=VersionOut.model_validate(version),
        department=DepartmentOut.model_validate(dept),
        format=_format_out(fmt),
        editable=is_editable(user, version.status, submission),
        rows=rows,
        month_totals=month_totals,
        grand_total=round(sum(month_totals.values()), 2),
        resolved_account=(
            ExpenseFormatAccountMapOut(
                function=account_map.function,
                account_id=account_map.account_id,
                account_code=account_map.account.code if account_map.account else None,
                account_name=account_map.account.name if account_map.account else None,
            )
            if account_map
            else None
        ),
    )


@router.put("/expense/grid", response_model=dict, summary="批次儲存費用預算")
def save_grid(
    payload: ExpenseSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    version = _get_version(db, payload.version_id)
    if db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    fmt = db.get(ExpenseFormat, payload.format_id)
    if fmt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")
    assert_expense_format_access(db, user, payload.department_id, payload.format_id)

    submission = _get_submission(db, payload.version_id, payload.department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    valid_keys = {c.key for c in fmt.columns}
    existing = {
        (e.column_key, e.month): e
        for e in db.scalars(
            select(ExpenseEntry).where(
                ExpenseEntry.version_id == payload.version_id,
                ExpenseEntry.department_id == payload.department_id,
                ExpenseEntry.format_id == payload.format_id,
            )
        )
    }
    now = datetime.now(timezone.utc)
    updated = 0
    for cell in payload.cells:
        if cell.column_key not in valid_keys:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"欄位 {cell.column_key} 不屬於此格式")
        key = (cell.column_key, cell.month)
        entry = existing.get(key)
        if cell.amount == 0 and entry is not None:
            db.delete(entry)
            existing.pop(key, None)
            continue
        if cell.amount == 0:
            continue
        if entry is None:
            entry = ExpenseEntry(
                version_id=payload.version_id,
                department_id=payload.department_id,
                format_id=payload.format_id,
                column_key=cell.column_key,
                month=cell.month,
                amount=cell.amount,
                updated_by=user.id,
            )
            existing[key] = entry
        else:
            entry.amount = cell.amount
            entry.updated_at = now
            entry.updated_by = user.id
        db.add(entry)
        updated += 1
    db.commit()
    return {"cells_updated": updated}


@router.post("/expense/sync", response_model=ExpenseSyncResult, summary="同步此格式金額至對應會計科目")
def sync_to_budget(
    version_id: int,
    department_id: int,
    format_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExpenseSyncResult:
    version = _get_version(db, version_id)
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    fmt = db.get(ExpenseFormat, format_id)
    if fmt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")
    assert_expense_format_access(db, user, department_id, format_id)

    submission = _get_submission(db, version_id, department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    account_map = _resolve_account(fmt, dept.function)
    if account_map is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"此部門功能別({dept.function.value if dept.function else '未設定'})尚未設定對應科目"
        )

    entries = db.scalars(
        select(ExpenseEntry).where(
            ExpenseEntry.version_id == version_id,
            ExpenseEntry.department_id == department_id,
            ExpenseEntry.format_id == format_id,
        )
    ).all()
    by_month: dict[int, float] = {}
    for e in entries:
        by_month[e.month] = by_month.get(e.month, 0.0) + float(e.amount or 0)

    existing = {
        e.month: e
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == version_id,
                BudgetEntry.department_id == department_id,
                BudgetEntry.account_id == account_map.account_id,
            )
        )
    }
    now = datetime.now(timezone.utc)
    for month in MONTHS:
        amount = round(by_month.get(month, 0.0), 2)
        entry = existing.get(month)
        if entry is None:
            if amount == 0:
                continue
            db.add(
                BudgetEntry(
                    version_id=version_id,
                    department_id=department_id,
                    account_id=account_map.account_id,
                    month=month,
                    amount=amount,
                    updated_by=user.id,
                )
            )
        else:
            entry.amount = amount
            entry.updated_at = now
            entry.updated_by = user.id
            db.add(entry)
    db.commit()
    return ExpenseSyncResult(accounts_updated=1, grand_total=round(sum(by_month.values()), 2))
