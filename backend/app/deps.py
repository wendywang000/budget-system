from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AccessGrant, GrantModule, User, UserRole
from .security import decode_access_token
from .services.tree import descendant_department_ids

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未提供憑證")
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "憑證無效或已過期")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "帳號不存在或已停用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.finance_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "此操作僅限財務管理者")
    return user


def accessible_department_ids(
    db: Session, user: User, module: GrantModule = GrantModule.budget
) -> set[int] | None:
    """回傳使用者在指定模組下可存取的部門 id 集合(含子部門);None 代表不限制(財務管理者)。

    dept_user 預設可存取自己部門(僅 budget 模組),另外可疊加 AccessGrant 額外授予的部門/模組, "
    每一筆授權都會展開含其子部門。
    """
    if user.role == UserRole.finance_admin:
        return None

    roots: set[int] = set()
    if module == GrantModule.budget and user.department_id is not None:
        roots.add(user.department_id)
    # 只採計「整部門」授權(未指定銷售人員/費用格式的細部範圍);更細的範圍由各模組自行檢查。
    grants = db.scalars(
        select(AccessGrant.department_id).where(
            AccessGrant.user_id == user.id,
            AccessGrant.module == module,
            AccessGrant.salesperson_id.is_(None),
            AccessGrant.expense_format_id.is_(None),
        )
    ).all()
    roots.update(grants)

    allowed: set[int] = set()
    for root_id in roots:
        allowed |= descendant_department_ids(db, root_id)
    return allowed


def accessible_salesperson_ids(db: Session, user: User) -> set[int] | None:
    """回傳使用者在銷售量預算模組下,額外被指定可處理的銷售人員 id;None 代表不限制(財務管理者)。"""
    if user.role == UserRole.finance_admin:
        return None
    return set(
        db.scalars(
            select(AccessGrant.salesperson_id).where(
                AccessGrant.user_id == user.id,
                AccessGrant.module == GrantModule.sales,
                AccessGrant.salesperson_id.is_not(None),
            )
        ).all()
    )


def assert_salesperson_access(db: Session, user: User, salesperson_department_id: int, salesperson_id: int) -> None:
    """銷售量預算的存取判斷:整部門授權(sales 模組)或指定該銷售人員授權,兩者符合其一即可。"""
    if user.role == UserRole.finance_admin:
        return
    if salesperson_id in accessible_salesperson_ids(db, user):
        return
    dept_scope = accessible_department_ids(db, user, GrantModule.sales)
    if dept_scope is not None and salesperson_department_id in dept_scope:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該銷售人員的資料")


def accessible_expense_format_ids(db: Session, user: User, department_id: int) -> set[int] | None:
    """回傳使用者對某部門而言,在費用預算模組下額外被指定可處理的費用格式 id;None 代表不限制。"""
    if user.role == UserRole.finance_admin:
        return None
    return set(
        db.scalars(
            select(AccessGrant.expense_format_id).where(
                AccessGrant.user_id == user.id,
                AccessGrant.module == GrantModule.expense,
                AccessGrant.department_id == department_id,
                AccessGrant.expense_format_id.is_not(None),
            )
        ).all()
    )


def assert_expense_format_access(db: Session, user: User, department_id: int, format_id: int) -> None:
    """費用預算的存取判斷:該部門的整部門授權(expense 模組)或該部門下指定該費用格式的授權,符合其一即可。"""
    if user.role == UserRole.finance_admin:
        return
    dept_scope = accessible_department_ids(db, user, GrantModule.expense)
    if dept_scope is not None and department_id in dept_scope:
        return
    if format_id in accessible_expense_format_ids(db, user, department_id):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該部門此費用格式的資料")


def assert_department_access(
    db: Session, user: User, department_id: int, module: GrantModule = GrantModule.budget
) -> None:
    allowed = accessible_department_ids(db, user, module)
    if allowed is not None and department_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該部門的資料")
