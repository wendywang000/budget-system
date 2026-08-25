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
    AssetCategory,
    BudgetEntry,
    BudgetVersion,
    CapexItem,
    Customer,
    Department,
    Product,
    SalesBudgetEntry,
    Salesperson,
    Submission,
    User,
    VersionStatus,
)
from ..schemas import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    AssetCategoryCreate,
    AssetCategoryOut,
    AssetCategoryUpdate,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    SalespersonCreate,
    SalespersonOut,
    SalespersonUpdate,
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
    db.query(SalesBudgetEntry).filter(SalesBudgetEntry.version_id == version_id).delete()
    db.query(CapexItem).filter(CapexItem.version_id == version_id).delete()
    db.delete(version)
    db.commit()


def _clear_other_defaults(db: Session, keep_id: int) -> None:
    others = db.scalars(
        select(BudgetVersion).where(BudgetVersion.id != keep_id, BudgetVersion.is_default.is_(True))
    ).all()
    for other in others:
        other.is_default = False
        db.add(other)


# --------------------------------------------------------------------------- #
# 產品主檔
# --------------------------------------------------------------------------- #
@router.get("/products", response_model=list[ProductOut], summary="產品清單")
def list_products(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    stmt = select(Product).order_by(Product.code)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    return [ProductOut.model_validate(p) for p in db.scalars(stmt)]


@router.post("/products", response_model=ProductOut, status_code=201, summary="新增產品")
def create_product(
    payload: ProductCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductOut:
    if db.scalar(select(Product).where(Product.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "產品代號已存在")
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return ProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductOut, summary="修改產品")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "產品不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != product.code:
        if db.scalar(select(Product).where(Product.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "產品代號已存在")
    for field, value in data.items():
        setattr(product, field, value)
    db.add(product)
    db.commit()
    db.refresh(product)
    return ProductOut.model_validate(product)


@router.delete("/products/{product_id}", status_code=204, response_model=None, summary="刪除產品")
def delete_product(
    product_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "產品不存在")
    used = db.scalar(
        select(func.count()).select_from(SalesBudgetEntry).where(SalesBudgetEntry.product_id == product_id)
    )
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此產品已有銷售量預算資料,請改為停用")
    db.delete(product)
    db.commit()


# --------------------------------------------------------------------------- #
# 客戶主檔
# --------------------------------------------------------------------------- #
@router.get("/customers", response_model=list[CustomerOut], summary="客戶清單")
def list_customers(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CustomerOut]:
    stmt = select(Customer).order_by(Customer.code)
    if active_only:
        stmt = stmt.where(Customer.is_active.is_(True))
    return [CustomerOut.model_validate(c) for c in db.scalars(stmt)]


@router.post("/customers", response_model=CustomerOut, status_code=201, summary="新增客戶")
def create_customer(
    payload: CustomerCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CustomerOut:
    if db.scalar(select(Customer).where(Customer.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "客戶代號已存在")
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerOut, summary="修改客戶")
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CustomerOut:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "客戶不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != customer.code:
        if db.scalar(select(Customer).where(Customer.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "客戶代號已存在")
    for field, value in data.items():
        setattr(customer, field, value)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.delete("/customers/{customer_id}", status_code=204, response_model=None, summary="刪除客戶")
def delete_customer(
    customer_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "客戶不存在")
    used = db.scalar(
        select(func.count()).select_from(SalesBudgetEntry).where(SalesBudgetEntry.customer_id == customer_id)
    )
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此客戶已有銷售量預算資料,請改為停用")
    db.delete(customer)
    db.commit()


# --------------------------------------------------------------------------- #
# 銷售人員主檔
# --------------------------------------------------------------------------- #
def _salesperson_out(sp: Salesperson) -> SalespersonOut:
    return SalespersonOut(
        id=sp.id,
        code=sp.code,
        name=sp.name,
        department_id=sp.department_id,
        is_active=sp.is_active,
        department_name=sp.department.name if sp.department else None,
    )


@router.get("/salespeople", response_model=list[SalespersonOut], summary="銷售人員清單")
def list_salespeople(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SalespersonOut]:
    stmt = select(Salesperson).order_by(Salesperson.code)
    if active_only:
        stmt = stmt.where(Salesperson.is_active.is_(True))
    return [_salesperson_out(sp) for sp in db.scalars(stmt)]


@router.post("/salespeople", response_model=SalespersonOut, status_code=201, summary="新增銷售人員")
def create_salesperson(
    payload: SalespersonCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SalespersonOut:
    if db.scalar(select(Salesperson).where(Salesperson.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "銷售人員代號已存在")
    if db.get(Department, payload.department_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算單位(部門)不存在")
    sp = Salesperson(**payload.model_dump())
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return _salesperson_out(sp)


@router.patch("/salespeople/{salesperson_id}", response_model=SalespersonOut, summary="修改銷售人員")
def update_salesperson(
    salesperson_id: int,
    payload: SalespersonUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SalespersonOut:
    sp = db.get(Salesperson, salesperson_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "銷售人員不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != sp.code:
        if db.scalar(select(Salesperson).where(Salesperson.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "銷售人員代號已存在")
    if "department_id" in data and db.get(Department, data["department_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算單位(部門)不存在")
    for field, value in data.items():
        setattr(sp, field, value)
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return _salesperson_out(sp)


@router.delete("/salespeople/{salesperson_id}", status_code=204, response_model=None, summary="刪除銷售人員")
def delete_salesperson(
    salesperson_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    sp = db.get(Salesperson, salesperson_id)
    if sp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "銷售人員不存在")
    used = db.scalar(
        select(func.count()).select_from(SalesBudgetEntry).where(SalesBudgetEntry.salesperson_id == salesperson_id)
    )
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此銷售人員已有銷售量預算資料,請改為停用")
    db.delete(sp)
    db.commit()


# --------------------------------------------------------------------------- #
# 資產類別主檔
# --------------------------------------------------------------------------- #
def _asset_category_out(cat: AssetCategory) -> AssetCategoryOut:
    return AssetCategoryOut(
        id=cat.id,
        code=cat.code,
        name=cat.name,
        depreciation_months=cat.depreciation_months,
        asset_account_id=cat.asset_account_id,
        expense_account_id=cat.expense_account_id,
        is_active=cat.is_active,
        asset_account_code=cat.asset_account.code if cat.asset_account else None,
        expense_account_code=cat.expense_account.code if cat.expense_account else None,
    )


@router.get("/asset-categories", response_model=list[AssetCategoryOut], summary="資產類別清單")
def list_asset_categories(
    active_only: bool = True,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AssetCategoryOut]:
    stmt = select(AssetCategory).order_by(AssetCategory.code)
    if active_only:
        stmt = stmt.where(AssetCategory.is_active.is_(True))
    return [_asset_category_out(c) for c in db.scalars(stmt)]


@router.post("/asset-categories", response_model=AssetCategoryOut, status_code=201, summary="新增資產類別")
def create_asset_category(
    payload: AssetCategoryCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AssetCategoryOut:
    if db.scalar(select(AssetCategory).where(AssetCategory.code == payload.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "資產類別代號已存在")
    cat = AssetCategory(**payload.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _asset_category_out(cat)


@router.patch("/asset-categories/{category_id}", response_model=AssetCategoryOut, summary="修改資產類別")
def update_asset_category(
    category_id: int,
    payload: AssetCategoryUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AssetCategoryOut:
    cat = db.get(AssetCategory, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "資產類別不存在")
    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] != cat.code:
        if db.scalar(select(AssetCategory).where(AssetCategory.code == data["code"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "資產類別代號已存在")
    for field, value in data.items():
        setattr(cat, field, value)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return _asset_category_out(cat)


@router.delete("/asset-categories/{category_id}", status_code=204, response_model=None, summary="刪除資產類別")
def delete_asset_category(
    category_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    cat = db.get(AssetCategory, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "資產類別不存在")
    used = db.scalar(select(func.count()).select_from(CapexItem).where(CapexItem.asset_category_id == category_id))
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, "此資產類別已有資本支出資料,請改為停用")
    db.delete(cat)
    db.commit()
