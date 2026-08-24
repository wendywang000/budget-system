from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole
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


def accessible_department_ids(db: Session, user: User) -> set[int] | None:
    """回傳使用者可存取的部門 id 集合;None 代表不限制(財務管理者)。"""
    if user.role == UserRole.finance_admin:
        return None
    if user.department_id is None:
        return set()
    return descendant_department_ids(db, user.department_id)


def assert_department_access(db: Session, user: User, department_id: int) -> None:
    allowed = accessible_department_ids(db, user)
    if allowed is not None and department_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "無權存取該部門的資料")
