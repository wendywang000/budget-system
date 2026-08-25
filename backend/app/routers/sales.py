"""銷售量預算:版本 × 銷售人員 × 客戶 × 產品 × 幣別 × 月份,可同步至收入科目。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    accessible_department_ids,
    accessible_salesperson_ids,
    assert_department_access,
    assert_salesperson_access,
    get_current_user,
)
from ..models import (
    BudgetEntry,
    BudgetVersion,
    Customer,
    Department,
    GrantModule,
    Product,
    SalesBudgetEntry,
    Salesperson,
    Submission,
    User,
    UserRole,
)
from ..schemas import (
    DepartmentOut,
    SalesBudgetCellOut,
    SalesBudgetGridResponse,
    SalesBudgetSaveRequest,
    SalesBudgetSyncResult,
    SalespersonOut,
    VersionOut,
)
from ..services.workflow import is_editable

router = APIRouter(prefix="/sales-budget", tags=["銷售量預算"])

MONTHS = tuple(range(1, 13))


def _get_version(db: Session, version_id: int) -> BudgetVersion:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算版本不存在")
    return version


def _get_salesperson(db: Session, salesperson_id: int) -> Salesperson:
    sp = db.get(Salesperson, salesperson_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "銷售人員不存在")
    return sp


def _get_submission(db: Session, version_id: int, department_id: int) -> Submission | None:
    return db.scalar(
        select(Submission).where(
            Submission.version_id == version_id,
            Submission.department_id == department_id,
        )
    )


def _salesperson_out(sp: Salesperson) -> SalespersonOut:
    return SalespersonOut(
        id=sp.id,
        code=sp.code,
        name=sp.name,
        department_id=sp.department_id,
        is_active=sp.is_active,
        department_name=sp.department.name if sp.department else None,
    )


@router.get("/my-salespeople", response_model=list[SalespersonOut], summary="我可填報的銷售人員清單")
def my_salespeople(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SalespersonOut]:
    people = db.scalars(select(Salesperson).where(Salesperson.is_active.is_(True))).all()
    if user.role == UserRole.finance_admin:
        allowed_ids = None
    else:
        dept_scope = accessible_department_ids(db, user, GrantModule.sales)
        person_scope = accessible_salesperson_ids(db, user)
        allowed_ids = {p.id for p in people if (dept_scope is not None and p.department_id in dept_scope)} | person_scope
    result = [p for p in people if allowed_ids is None or p.id in allowed_ids]
    return [_salesperson_out(p) for p in sorted(result, key=lambda p: p.code)]


@router.get("/grid", response_model=SalesBudgetGridResponse, summary="取得某銷售人員某版本的銷售量預算表")
def get_grid(
    version_id: int,
    salesperson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesBudgetGridResponse:
    version = _get_version(db, version_id)
    salesperson = _get_salesperson(db, salesperson_id)
    dept = db.get(Department, salesperson.department_id)
    assert_salesperson_access(db, user, salesperson.department_id, salesperson.id)

    entries = db.scalars(
        select(SalesBudgetEntry).where(
            SalesBudgetEntry.version_id == version_id,
            SalesBudgetEntry.salesperson_id == salesperson_id,
        )
    ).all()

    customers = {c.id: c for c in db.scalars(select(Customer))}
    products = {p.id: p for p in db.scalars(select(Product))}

    grouped: dict[tuple[int, int], dict] = {}
    for entry in entries:
        key = (entry.customer_id, entry.product_id)
        bucket = grouped.setdefault(key, {"months": {}, "note": None, "currency": entry.currency})
        bucket["months"][entry.month] = {
            "quantity": float(entry.quantity or 0),
            "amount": float(entry.amount or 0),
        }
        if entry.note:
            bucket["note"] = entry.note

    rows: list[SalesBudgetCellOut] = []
    month_totals = {m: 0.0 for m in MONTHS}
    grand_total = 0.0

    for (customer_id, product_id), data in sorted(
        grouped.items(), key=lambda kv: (customers[kv[0][0]].code, products[kv[0][1]].code)
    ):
        customer = customers.get(customer_id)
        product = products.get(product_id)
        if customer is None or product is None:
            continue
        months = {m: data["months"].get(m, {"quantity": 0.0, "amount": 0.0}) for m in MONTHS}
        total_qty = round(sum(v["quantity"] for v in months.values()), 2)
        total_amt = round(sum(v["amount"] for v in months.values()), 2)
        for m in MONTHS:
            month_totals[m] = round(month_totals[m] + months[m]["amount"], 2)
        grand_total = round(grand_total + total_amt, 2)
        rows.append(
            SalesBudgetCellOut(
                customer_id=customer.id,
                customer_code=customer.code,
                customer_name=customer.name,
                product_id=product.id,
                product_code=product.code,
                product_name=product.name,
                unit=product.unit,
                currency=data["currency"],
                months=months,
                total_quantity=total_qty,
                total_amount=total_amt,
                note=data["note"],
            )
        )

    submission = _get_submission(db, version_id, salesperson.department_id) if dept else None
    return SalesBudgetGridResponse(
        version=VersionOut.model_validate(version),
        department=DepartmentOut.model_validate(dept) if dept else None,
        salesperson=_salesperson_out(salesperson),
        editable=is_editable(user, version.status, submission),
        rows=rows,
        month_totals=month_totals,
        grand_total=grand_total,
    )


@router.put("/grid", response_model=SalesBudgetSyncResult, summary="批次儲存某銷售人員的銷售量預算")
def save_grid(
    payload: SalesBudgetSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesBudgetSyncResult:
    version = _get_version(db, payload.version_id)
    salesperson = _get_salesperson(db, payload.salesperson_id)
    assert_salesperson_access(db, user, salesperson.department_id, salesperson.id)

    submission = _get_submission(db, payload.version_id, salesperson.department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此銷售人員目前不可編輯")

    valid_customers = {c.id for c in db.scalars(select(Customer).where(Customer.is_active.is_(True)))}
    valid_products = {p.id for p in db.scalars(select(Product).where(Product.is_active.is_(True)))}

    existing = {
        (e.customer_id, e.product_id, e.month): e
        for e in db.scalars(
            select(SalesBudgetEntry).where(
                SalesBudgetEntry.version_id == payload.version_id,
                SalesBudgetEntry.salesperson_id == payload.salesperson_id,
            )
        )
    }

    now = datetime.now(timezone.utc)
    updated = 0
    for cell in payload.cells:
        if cell.customer_id not in valid_customers:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"客戶 {cell.customer_id} 不存在或已停用")
        if cell.product_id not in valid_products:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"產品 {cell.product_id} 不存在或已停用")
        key = (cell.customer_id, cell.product_id, cell.month)
        entry = existing.get(key)

        if cell.quantity == 0 and cell.amount == 0:
            if entry is not None and not entry.note:
                db.delete(entry)
                existing.pop(key, None)
            elif entry is not None:
                entry.quantity = 0
                entry.amount = 0
                entry.updated_at = now
                entry.updated_by = user.id
                db.add(entry)
            continue

        if entry is None:
            entry = SalesBudgetEntry(
                version_id=payload.version_id,
                department_id=salesperson.department_id,
                salesperson_id=payload.salesperson_id,
                customer_id=cell.customer_id,
                product_id=cell.product_id,
                month=cell.month,
                currency=cell.currency or "TWD",
                quantity=cell.quantity,
                amount=cell.amount,
                updated_by=user.id,
            )
            existing[key] = entry
        else:
            entry.currency = cell.currency or entry.currency
            entry.quantity = cell.quantity
            entry.amount = cell.amount
            entry.updated_at = now
            entry.updated_by = user.id
        db.add(entry)
        updated += 1

    for combo_key, note in payload.notes.items():
        try:
            customer_id_str, product_id_str = combo_key.split("-")
            customer_id, product_id = int(customer_id_str), int(product_id_str)
        except ValueError:
            continue
        text = (note or "").strip() or None
        row_entries = [e for (cid, pid, _m), e in existing.items() if cid == customer_id and pid == product_id]
        if not row_entries:
            if text is None:
                continue
            placeholder = SalesBudgetEntry(
                version_id=payload.version_id,
                department_id=salesperson.department_id,
                salesperson_id=payload.salesperson_id,
                customer_id=customer_id,
                product_id=product_id,
                month=1,
                quantity=0,
                amount=0,
                note=text,
                updated_by=user.id,
            )
            db.add(placeholder)
            continue
        for entry in row_entries:
            entry.note = text
            db.add(entry)

    db.commit()

    total = sum(
        float(e.amount or 0)
        for e in db.scalars(
            select(SalesBudgetEntry).where(
                SalesBudgetEntry.version_id == payload.version_id,
                SalesBudgetEntry.salesperson_id == payload.salesperson_id,
            )
        )
    )
    return SalesBudgetSyncResult(accounts_updated=0, cells_updated=updated, grand_total=round(total, 2))


@router.post("/sync", response_model=SalesBudgetSyncResult, summary="同步某部門的銷售量預算金額至收入科目預算表")
def sync_to_budget(
    version_id: int,
    department_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SalesBudgetSyncResult:
    """把該部門所有銷售人員、每個產品對應收入科目、逐月加總的銷售金額,寫入 BudgetEntry。

    沒有設定收入科目的產品會被略過(金額不會消失,只是不會自動回填到科目表)。
    """
    version = _get_version(db, version_id)
    if db.get(Department, department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    assert_department_access(db, user, department_id, GrantModule.sales)

    submission = _get_submission(db, version_id, department_id)
    if not is_editable(user, version.status, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    entries = db.scalars(
        select(SalesBudgetEntry).where(
            SalesBudgetEntry.version_id == version_id,
            SalesBudgetEntry.department_id == department_id,
        )
    ).all()
    products = {p.id: p for p in db.scalars(select(Product))}

    by_account_month: dict[tuple[int, int], float] = {}
    for entry in entries:
        product = products.get(entry.product_id)
        if product is None or product.revenue_account_id is None:
            continue
        key = (product.revenue_account_id, entry.month)
        by_account_month[key] = by_account_month.get(key, 0.0) + float(entry.amount or 0)

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
    grand_total = round(sum(by_account_month.values()), 2)
    return SalesBudgetSyncResult(
        accounts_updated=len(touched_accounts),
        cells_updated=len(by_account_month),
        grand_total=grand_total,
    )
