"""權限授予:人 × 模組(銷售量預算/費用預算/資本支出/報表查詢)× 部門,可再細至銷售人員或費用格式。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import AccessGrant, Department, ExpenseFormat, Salesperson, User
from ..schemas import AccessGrantCreate, AccessGrantOut

router = APIRouter(prefix="/access-grants", tags=["權限授予"])


def _to_out(grant: AccessGrant, db: Session) -> AccessGrantOut:
    user = db.get(User, grant.user_id)
    dept = db.get(Department, grant.department_id)
    sp = db.get(Salesperson, grant.salesperson_id) if grant.salesperson_id else None
    fmt = db.get(ExpenseFormat, grant.expense_format_id) if grant.expense_format_id else None
    return AccessGrantOut(
        id=grant.id,
        user_id=grant.user_id,
        user_name=user.full_name if user else None,
        module=grant.module,
        department_id=grant.department_id,
        department_name=dept.name if dept else None,
        salesperson_id=grant.salesperson_id,
        salesperson_name=sp.name if sp else None,
        expense_format_id=grant.expense_format_id,
        expense_format_name=fmt.name if fmt else None,
        created_at=grant.created_at,
    )


@router.get("", response_model=list[AccessGrantOut], summary="權限授予清單")
def list_grants(
    user_id: int | None = None,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AccessGrantOut]:
    stmt = select(AccessGrant)
    if user_id is not None:
        stmt = stmt.where(AccessGrant.user_id == user_id)
    grants = db.scalars(stmt).all()
    return [_to_out(g, db) for g in grants]


@router.post("", response_model=AccessGrantOut, status_code=201, summary="新增權限授予")
def create_grant(
    payload: AccessGrantCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AccessGrantOut:
    if db.get(User, payload.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "使用者不存在")
    if db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    if payload.salesperson_id is not None and db.get(Salesperson, payload.salesperson_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "銷售人員不存在")
    if payload.expense_format_id is not None and db.get(ExpenseFormat, payload.expense_format_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "費用格式不存在")

    existing = db.scalar(
        select(AccessGrant).where(
            AccessGrant.user_id == payload.user_id,
            AccessGrant.module == payload.module,
            AccessGrant.department_id == payload.department_id,
            AccessGrant.salesperson_id == payload.salesperson_id,
            AccessGrant.expense_format_id == payload.expense_format_id,
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "此授權已存在")

    grant = AccessGrant(**payload.model_dump())
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return _to_out(grant, db)


@router.delete("/{grant_id}", status_code=204, response_model=None, summary="刪除權限授予")
def delete_grant(
    grant_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    grant = db.get(AccessGrant, grant_id)
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "授權不存在")
    db.delete(grant)
    db.commit()
