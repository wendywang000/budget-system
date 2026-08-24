from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User, UserRole
from ..schemas import (
    LoginRequest,
    PasswordChange,
    TokenOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["認證"])


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        department_id=user.department_id,
        department_name=user.department.name if user.department else None,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenOut, summary="登入取得 Token")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "帳號或密碼錯誤")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "帳號已停用")
    token = create_access_token(user.id, {"role": user.role.value})
    return TokenOut(access_token=token, user=_to_out(user))


@router.get("/me", response_model=UserOut, summary="取得目前登入者")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _to_out(user)


@router.post("/change-password", summary="變更自己的密碼")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "原密碼錯誤")
    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return {"detail": "密碼已更新"}


# --------------------------------------------------------------------------- #
# 使用者維護(僅財務管理者)
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=list[UserOut], summary="使用者清單")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.username)).all()
    return [_to_out(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201, summary="新增使用者")
def create_user(
    payload: UserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "帳號已存在")
    if payload.role == UserRole.dept_user and payload.department_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "部門使用者必須指定所屬部門")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        department_id=payload.department_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_out(user)


@router.patch("/users/{user_id}", response_model=UserOut, summary="修改使用者")
def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "使用者不存在")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.password_hash = hash_password(password)
    for field, value in data.items():
        setattr(user, field, value)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_out(user)
