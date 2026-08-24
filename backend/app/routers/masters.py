"""主檔維護:部門(成本中心)、會計科目、預算版本。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import accessible_department_ids, get_current_user, require_admin
from ..models import (
    Account,
    Actual,
    BudgetEntry,
    BudgetVersion,
    Department,
    Submission,
    User,
    VersionStatus,
)
from ..schemas import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    VersionCreate,
    VersionOut,
    VersionUpdate,
)
from ..services.tree import (
    has_children_map,
    load_accounts,
    load_departments,
    ordered_tree,
)

router = APIRouter(tags=["主檔"])


# --------------------------------------------------------------------------- #
# 部門
# --------------------------------------------------------------------------- #
@router.get("/departments", response_model=list[DepartmentOut], summary="部門樹(深度優先排序)")
def list_departments(
    active_only: bool = True,
    accessible_only: bool = Query(False, description="只回傳目前使用者有權編列的部門"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DepartmentOut]:
    departments = load_departments(db, active_only=active_only)
    child_flags = has_children_map(departments)
    allowed = accessible_department_ids(db, user)

    rows: list[DepartmentOut] = []
    for dept, level in ordered_tree(departments):
        if accessible_only and allowed is not None and dept.id not in allowed:
            continue
        out = DepartmentOut.model_validate(dept)
        out.level = level
        out.has_children = child_flags.get(dept.id, False)
        rows.append(out)
    return rows


@router.post("/departments", response_model=DepartmentOut, status_code=201, summary="新增部門")
def create_department(
    payload: DepartmentCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DepartmentOut:
    if db.scalar(select(Department).where(Department.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "部門代號已存在")
    if payload.parent_id and db.get(Department, payload.parent_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上層部門不存在")
    dept = Department(**payload.model_dump())
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.patch("/departments/{dept_id}", response_model=DepartmentOut, summary="修改部門")
def update_department(
    dept_id: int,
    payload: DepartmentUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DepartmentOut:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("parent_id") == dept_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上層部門不可指向自己")
    if "code" in data and data["code"] != dept.code:
        if db.scalar(select(Department).where(Department.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "部門代號已存在")
    for field, value in data.items():
        setattr(dept, field, value)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.delete("/departments/{dept_id}", status_code=204, response_model=None, summary="刪除部門")
def delete_department(
    dept_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    if db.scalar(select(func.count()).select_from(Department).where(Department.parent_id == dept_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "此部門仍有下層部門,無法刪除")
    used = db.scalar(select(func.count()).select_from(BudgetEntry).where(BudgetEntry.department_id == dept_id))
    used += db.scalar(select(func.count()).select_from(Actual).where(Actual.department_id == dept_id)) or 0
    used += db.scalar(select(func.count()).select_from(User).where(User.department_id == dept_id)) or 0
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此部門已有預算/實際數/使用者,請改為停用")
    db.delete(dept)
    db.commit()


# --------------------------------------------------------------------------- #
# 科目
# --------------------------------------------------------------------------- #
@router.get("/accounts", response_model=list[AccountOut], summary="科目樹(深度優先排序)")
def list_accounts(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AccountOut]:
    accounts = load_accounts(db, active_only=active_only)
    child_flags = has_children_map(accounts)
    rows: list[AccountOut] = []
    for account, level in ordered_tree(accounts):
        out = AccountOut.model_validate(account)
        out.level = level
        out.has_children = child_flags.get(account.id, False)
        rows.append(out)
    return rows


@router.post("/accounts", response_model=AccountOut, status_code=201, summary="新增科目")
def create_account(
    payload: AccountCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    if db.scalar(select(Account).where(Account.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "科目代號已存在")
    if payload.parent_id and db.get(Account, payload.parent_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上層科目不存在")
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountOut.model_validate(account)


@router.patch("/accounts/{account_id}", response_model=AccountOut, summary="修改科目")
def update_account(
    account_id: int,
    payload: AccountUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccountOut:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "科目不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("parent_id") == account_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上層科目不可指向自己")
    if "code" in data and data["code"] != account.code:
        if db.scalar(select(Account).where(Account.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "科目代號已存在")
    for field, value in data.items():
        setattr(account, field, value)
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountOut.model_validate(account)


@router.delete("/accounts/{account_id}", status_code=204, response_model=None, summary="刪除科目")
def delete_account(
    account_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "科目不存在")
    if db.scalar(select(func.count()).select_from(Account).where(Account.parent_id == account_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "此科目仍有子科目,無法刪除")
    used = db.scalar(select(func.count()).select_from(BudgetEntry).where(BudgetEntry.account_id == account_id)) or 0
    used += db.scalar(select(func.count()).select_from(Actual).where(Actual.account_id == account_id)) or 0
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此科目已有預算/實際數,請改為停用")
    db.delete(account)
    db.commit()


# --------------------------------------------------------------------------- #
# 預算版本
# --------------------------------------------------------------------------- #
@router.get("/versions", response_model=list[VersionOut], summary="版本清單")
def list_versions(
    fiscal_year: int | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VersionOut]:
    stmt = select(BudgetVersion).order_by(BudgetVersion.fiscal_year.desc(), BudgetVersion.name)
    if fiscal_year:
        stmt = stmt.where(BudgetVersion.fiscal_year == fiscal_year)
    return [VersionOut.model_validate(v) for v in db.scalars(stmt)]


@router.post("/versions", response_model=VersionOut, status_code=201, summary="新增版本(可由既有版本複製)")
def create_version(
    payload: VersionCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VersionOut:
    exists = db.scalar(
        select(BudgetVersion).where(
            BudgetVersion.fiscal_year == payload.fiscal_year,
            BudgetVersion.name == payload.name,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "同年度已有相同版本名稱")

    version = BudgetVersion(
        fiscal_year=payload.fiscal_year,
        name=payload.name,
        status=payload.status,
        is_default=payload.is_default,
        description=payload.description,
    )
    db.add(version)
    db.flush()

    if payload.copy_from_version_id:
        source = db.get(BudgetVersion, payload.copy_from_version_id)
        if source is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "來源版本不存在")
        entries = db.scalars(select(BudgetEntry).where(BudgetEntry.version_id == source.id)).all()
        for entry in entries:
            db.add(
                BudgetEntry(
                    version_id=version.id,
                    department_id=entry.department_id,
                    account_id=entry.account_id,
                    month=entry.month,
                    amount=round(float(entry.amount) * payload.copy_ratio, 2),
                    note=entry.note,
                )
            )

    if payload.is_default:
        _clear_other_defaults(db, version.id)

    db.commit()
    db.refresh(version)
    return VersionOut.model_validate(version)


@router.patch("/versions/{version_id}", response_model=VersionOut, summary="修改版本(開放 / 鎖定)")
def update_version(
    version_id: int,
    payload: VersionUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VersionOut:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(version, field, value)
    if data.get("is_default"):
        _clear_other_defaults(db, version.id)
    db.add(version)
    db.commit()
    db.refresh(version)
    return VersionOut.model_validate(version)


@router.delete("/versions/{version_id}", status_code=204, response_model=None, summary="刪除版本(連同其預算明細)")
def delete_version(
    version_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本不存在")
    if version.status == VersionStatus.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "已鎖定的版本不可刪除,請先解除鎖定")
    db.query(BudgetEntry).filter(BudgetEntry.version_id == version_id).delete()
    db.query(Submission).filter(Submission.version_id == version_id).delete()
    db.delete(version)
    db.commit()


def _clear_other_defaults(db: Session, keep_id: int) -> None:
    others = db.scalars(
        select(BudgetVersion).where(BudgetVersion.id != keep_id, BudgetVersion.is_default.is_(True))
    ).all()
    for other in others:
        other.is_default = False
        db.add(other)
