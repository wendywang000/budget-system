"""資本支出:項目一經核定即成為既有資產,依攤銷月數逐年自動算出應攤提折舊費用。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_department_ids, assert_department_access, get_current_user, require_admin
from ..models import (
    AssetCategory,
    BudgetEntry,
    BudgetVersion,
    CapexItem,
    CapexStatus,
    Department,
    GrantModule,
    User,
)
from ..schemas import CapexItemCreate, CapexItemOut, CapexItemUpdate, CapexSyncResult
from ..services.workflow import is_editable

router = APIRouter(prefix="/capex", tags=["資本支出編列"])


def _yyyymm_to_index(yyyymm: int) -> int:
    return (yyyymm // 100) * 12 + (yyyymm % 100)


def _monthly_depreciation(item: CapexItem) -> float:
    months = item.depreciation_months
    if not months:
        return 0.0
    return round(float(item.acquisition_cost or 0) / months, 2)


def _amount_in_month(item: CapexItem, yyyymm: int) -> float:
    """該資產在指定年月是否落在攤銷期間內,若是則回傳當月折舊金額,否則 0。"""
    months = item.depreciation_months
    if not months:
        return 0.0
    offset = _yyyymm_to_index(yyyymm) - _yyyymm_to_index(item.depreciation_start_yyyymm)
    if 0 <= offset < months:
        return _monthly_depreciation(item)
    return 0.0


def _get_version(db: Session, version_id: int) -> BudgetVersion:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算版本不存在")
    return version


def _get_submission(db: Session, version_id: int, department_id: int):
    from ..models import Submission

    return db.scalar(
        select(Submission).where(
            Submission.version_id == version_id,
            Submission.department_id == department_id,
        )
    )


def _to_out(item: CapexItem, db: Session, fiscal_year: int | None = None) -> CapexItemOut:
    dept = db.get(Department, item.department_id)
    category = db.get(AssetCategory, item.asset_category_id)
    expense_account = category.expense_account if category else None
    monthly = _monthly_depreciation(item)
    return CapexItemOut(
        id=item.id,
        version_id=item.version_id,
        department_id=item.department_id,
        asset_category_id=item.asset_category_id,
        name=item.name,
        acquisition_cost=float(item.acquisition_cost or 0),
        acquisition_yyyymm=item.acquisition_yyyymm,
        depreciation_start_yyyymm=item.depreciation_start_yyyymm,
        depreciation_months=item.depreciation_months,
        justification=item.justification,
        status=item.status,
        department_name=dept.name if dept else None,
        asset_category_name=category.name if category else None,
        expense_account_id=expense_account.id if expense_account else None,
        expense_account_code=expense_account.code if expense_account else None,
        expense_account_name=expense_account.name if expense_account else None,
        monthly_depreciation=monthly,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=list[CapexItemOut], summary="資本支出(資產)清單")
def list_items(
    version_id: int,
    department_id: int | None = None,
    include_prior_vintages: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CapexItemOut]:
    version = _get_version(db, version_id)
    allowed = accessible_department_ids(db, user, GrantModule.capex)

    if department_id is not None:
        assert_department_access(db, user, department_id, GrantModule.capex)

    if include_prior_vintages:
        # 同一部門在任何版本核定過的資產,只要攤銷期間仍與本版本年度有重疊,都算「既有資產」
        stmt = select(CapexItem)
        if department_id is not None:
            stmt = stmt.where(CapexItem.department_id == department_id)
        candidates = db.scalars(stmt).all()
        year_start, year_end = version.fiscal_year * 100 + 1, version.fiscal_year * 100 + 12

        def _visible(i: CapexItem) -> bool:
            if i.version_id == version_id:
                return True  # 本版本新提出的項目一律顯示,不論狀態
            if i.status != CapexStatus.approved or not i.depreciation_months:
                return False  # 其他版本尚未核定,或不攤銷(如土地)的項目不重複顯示為既有資產
            start_idx = _yyyymm_to_index(i.depreciation_start_yyyymm)
            return start_idx + i.depreciation_months > _yyyymm_to_index(year_start) and start_idx <= _yyyymm_to_index(
                year_end
            )

        items = [i for i in candidates if _visible(i)]
    else:
        stmt = select(CapexItem).where(CapexItem.version_id == version_id)
        if department_id is not None:
            stmt = stmt.where(CapexItem.department_id == department_id)
        items = db.scalars(stmt).all()

    if allowed is not None:
        items = [i for i in items if i.department_id in allowed]
    items.sort(key=lambda i: (i.acquisition_yyyymm, i.id))
    return [_to_out(i, db, version.fiscal_year) for i in items]


@router.post("", response_model=CapexItemOut, status_code=201, summary="新增資本支出項目")
def create_item(
    payload: CapexItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapexItemOut:
    version = _get_version(db, payload.version_id)
    if db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    category = db.get(AssetCategory, payload.asset_category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "資產類別不存在")
    assert_department_access(db, user, payload.department_id, GrantModule.capex)

    submission = _get_submission(db, payload.version_id, payload.department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    item = CapexItem(
        version_id=payload.version_id,
        department_id=payload.department_id,
        asset_category_id=payload.asset_category_id,
        name=payload.name,
        acquisition_cost=payload.acquisition_cost,
        acquisition_yyyymm=payload.acquisition_yyyymm,
        depreciation_start_yyyymm=payload.depreciation_start_yyyymm or payload.acquisition_yyyymm,
        depreciation_months=(
            payload.depreciation_months if payload.depreciation_months is not None else category.depreciation_months
        ),
        justification=payload.justification,
        created_by=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item, db)


@router.patch("/{item_id}", response_model=CapexItemOut, summary="修改資本支出項目")
def update_item(
    item_id: int,
    payload: CapexItemUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapexItemOut:
    item = db.get(CapexItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "項目不存在")
    version = _get_version(db, item.version_id)
    assert_department_access(db, user, item.department_id, GrantModule.capex)

    submission = _get_submission(db, item.version_id, item.department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    data = payload.model_dump(exclude_unset=True)
    if "asset_category_id" in data and db.get(AssetCategory, data["asset_category_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "資產類別不存在")
    for field, value in data.items():
        setattr(item, field, value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item, db)


@router.delete("/{item_id}", status_code=204, response_model=None, summary="刪除資本支出項目")
def delete_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = db.get(CapexItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "項目不存在")
    version = _get_version(db, item.version_id)
    assert_department_access(db, user, item.department_id, GrantModule.capex)
    submission = _get_submission(db, item.version_id, item.department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")
    db.delete(item)
    db.commit()


def _transition(db: Session, item: CapexItem, new_status: CapexStatus) -> CapexItemOut:
    item.status = new_status
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item, db)


@router.post("/{item_id}/submit", response_model=CapexItemOut, summary="送出單一項目")
def submit_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CapexItemOut:
    item = db.get(CapexItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "項目不存在")
    assert_department_access(db, user, item.department_id, GrantModule.capex)
    return _transition(db, item, CapexStatus.submitted)


@router.post("/{item_id}/approve", response_model=CapexItemOut, summary="核定單一項目(財務管理者)")
def approve_item(item_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> CapexItemOut:
    item = db.get(CapexItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "項目不存在")
    return _transition(db, item, CapexStatus.approved)


@router.post("/{item_id}/return", response_model=CapexItemOut, summary="退回單一項目(財務管理者)")
def return_item(item_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> CapexItemOut:
    item = db.get(CapexItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "項目不存在")
    return _transition(db, item, CapexStatus.returned)


@router.post("/sync", response_model=CapexSyncResult, summary="同步本年度應攤提折舊至費用預算表")
def sync_to_budget(
    version_id: int,
    department_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CapexSyncResult:
    """計算該部門「本版本新提出的項目」+「過去已核定、攤銷期間仍涵蓋本年度的既有資產」,

    逐月加總折舊金額,寫入各資產類別對應費用科目的 BudgetEntry。
    """
    version = _get_version(db, version_id)
    if db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    assert_department_access(db, user, department_id, GrantModule.capex)

    submission = _get_submission(db, version_id, department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    items = db.scalars(select(CapexItem).where(CapexItem.department_id == department_id)).all()
    items = [i for i in items if i.version_id == version_id or i.status == CapexStatus.approved]
    categories = {c.id: c for c in db.scalars(select(AssetCategory))}

    by_account_month: dict[tuple[int, int], float] = {}
    for item in items:
        category = categories.get(item.asset_category_id)
        if category is None or category.expense_account_id is None:
            continue
        for month in range(1, 13):
            yyyymm = version.fiscal_year * 100 + month
            amount = _amount_in_month(item, yyyymm)
            if amount == 0:
                continue
            key = (category.expense_account_id, month)
            by_account_month[key] = by_account_month.get(key, 0.0) + amount

    existing = {
        (e.account_id, e.month): e
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == version_id,
                BudgetEntry.department_id == department_id,
            )
        )
    }

    now = datetime.now(timezone.utc)
    touched_accounts: set[int] = set()
    for (account_id, month), amount in by_account_month.items():
        key = (account_id, month)
        entry = existing.get(key)
        rounded = round(amount, 2)
        if entry is None:
            db.add(
                BudgetEntry(
                    version_id=version_id,
                    department_id=department_id,
                    account_id=account_id,
                    month=month,
                    amount=rounded,
                    updated_by=user.id,
                )
            )
        else:
            entry.amount = rounded
            entry.updated_at = now
            entry.updated_by = user.id
            db.add(entry)
        touched_accounts.add(account_id)

    db.commit()
    return CapexSyncResult(accounts_updated=len(touched_accounts), grand_total=round(sum(by_account_month.values()), 2))
