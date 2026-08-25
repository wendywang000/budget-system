from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    AccountCategory,
    CapexStatus,
    DeptKind,
    ExpenseFunction,
    GrantModule,
    SubmissionStatus,
    UserRole,
    VersionStatus,
)

MONTHS = list(range(1, 13))


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# 認證
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    department_id: int | None
    department_name: str | None = None
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str
    password: str = Field(min_length=4)
    role: UserRole = UserRole.dept_user
    department_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=4)
    role: UserRole | None = None
    department_id: int | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=4)


# --------------------------------------------------------------------------- #
# 部門
# --------------------------------------------------------------------------- #
class DepartmentBase(BaseModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=100)
    name_zh_hans: str | None = None
    name_en: str | None = None
    kind: DeptKind = DeptKind.department
    parent_id: int | None = None
    manager: str | None = None
    function: ExpenseFunction | None = None
    sort_order: int = 0
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    name_zh_hans: str | None = None
    name_en: str | None = None
    kind: DeptKind | None = None
    parent_id: int | None = None
    manager: str | None = None
    function: ExpenseFunction | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DepartmentOut(ORMModel, DepartmentBase):
    id: int
    level: int = 0
    has_children: bool = False


# --------------------------------------------------------------------------- #
# 科目
# --------------------------------------------------------------------------- #
class AccountBase(BaseModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=100)
    category: AccountCategory
    parent_id: int | None = None
    is_postable: bool = True
    sort_order: int = 0
    is_active: bool = True
    note: str | None = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    category: AccountCategory | None = None
    parent_id: int | None = None
    is_postable: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    note: str | None = None


class AccountOut(ORMModel, AccountBase):
    id: int
    level: int = 0
    has_children: bool = False


# --------------------------------------------------------------------------- #
# 版本
# --------------------------------------------------------------------------- #
class VersionBase(BaseModel):
    fiscal_year: int = Field(ge=1900, le=2999)
    name: str = Field(max_length=60)
    status: VersionStatus = VersionStatus.open
    is_default: bool = False
    description: str | None = None


class VersionCreate(VersionBase):
    copy_from_version_id: int | None = None
    copy_ratio: float = 1.0


class VersionUpdate(BaseModel):
    name: str | None = None
    status: VersionStatus | None = None
    is_default: bool | None = None
    description: str | None = None


class VersionOut(ORMModel, VersionBase):
    id: int
    created_at: datetime


# --------------------------------------------------------------------------- #
# 預算表格
# --------------------------------------------------------------------------- #
class GridRow(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    category: AccountCategory
    level: int
    is_postable: bool
    months: dict[int, float] = Field(default_factory=dict)
    total: float = 0
    note: str | None = None


class GridResponse(BaseModel):
    version: VersionOut
    department: DepartmentOut
    editable: bool
    submission_status: SubmissionStatus
    submission_comment: str | None = None
    rows: list[GridRow]
    month_totals: dict[int, float]
    grand_total: float
    category_totals: dict[str, float]


class CellUpdate(BaseModel):
    account_id: int
    month: int = Field(ge=1, le=12)
    amount: float


class GridSaveRequest(BaseModel):
    version_id: int
    department_id: int
    cells: list[CellUpdate]
    notes: dict[int, str | None] = Field(default_factory=dict)


class GridSaveResult(BaseModel):
    updated: int
    deleted: int
    grand_total: float


class SubmissionOut(ORMModel):
    id: int | None = None
    version_id: int
    department_id: int
    department_code: str | None = None
    department_name: str | None = None
    status: SubmissionStatus
    comment: str | None = None
    total: float = 0
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None


class SubmissionAction(BaseModel):
    version_id: int
    department_id: int
    comment: str | None = None


# --------------------------------------------------------------------------- #
# 報表
# --------------------------------------------------------------------------- #
class SummaryRow(BaseModel):
    key: str
    code: str
    name: str
    level: int
    category: str | None = None
    months: dict[int, float]
    total: float
    is_group: bool = False


class SummaryResponse(BaseModel):
    version: VersionOut
    group_by: str
    rows: list[SummaryRow]
    month_totals: dict[int, float]
    grand_total: float


class VarianceRow(BaseModel):
    key: str
    code: str
    name: str
    level: int
    category: str | None = None
    is_group: bool = False
    budget: float
    actual: float
    variance: float
    achievement: float | None = None
    budget_ytd: float
    actual_ytd: float
    variance_ytd: float


class VarianceResponse(BaseModel):
    fiscal_year: int
    version: VersionOut
    through_month: int
    group_by: str
    rows: list[VarianceRow]
    totals: VarianceRow


class ActualCellIn(BaseModel):
    department_code: str
    account_code: str
    month: int = Field(ge=1, le=12)
    amount: float


class ActualUpsertRequest(BaseModel):
    fiscal_year: int
    rows: list[ActualCellIn]


class ImportResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 產品 / 客戶主檔
# --------------------------------------------------------------------------- #
class ProductBase(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=150)
    category: str | None = None
    unit: str = "PCS"
    unit_price: float = 0
    unit_cost: float = 0
    revenue_account_id: int | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    category: str | None = None
    unit: str | None = None
    unit_price: float | None = None
    unit_cost: float | None = None
    revenue_account_id: int | None = None
    is_active: bool | None = None


class ProductOut(ORMModel, ProductBase):
    id: int


class CustomerBase(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=150)
    region: str | None = None
    sales_rep: str | None = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    region: str | None = None
    sales_rep: str | None = None
    is_active: bool | None = None


class CustomerOut(ORMModel, CustomerBase):
    id: int


# --------------------------------------------------------------------------- #
# 銷售人員主檔
# --------------------------------------------------------------------------- #
class SalespersonBase(BaseModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=50)
    department_id: int
    is_active: bool = True


class SalespersonCreate(SalespersonBase):
    pass


class SalespersonUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    department_id: int | None = None
    is_active: bool | None = None


class SalespersonOut(ORMModel, SalespersonBase):
    id: int
    department_name: str | None = None


# --------------------------------------------------------------------------- #
# 銷售量預算
# --------------------------------------------------------------------------- #
class SalesBudgetCellOut(BaseModel):
    customer_id: int
    customer_code: str
    customer_name: str
    product_id: int
    product_code: str
    product_name: str
    unit: str
    currency: str = "TWD"
    months: dict[int, dict[str, float]]  # month -> {quantity, amount}
    total_quantity: float
    total_amount: float
    note: str | None = None


class SalesBudgetGridResponse(BaseModel):
    version: VersionOut
    department: DepartmentOut | None = None
    salesperson: SalespersonOut
    editable: bool
    rows: list[SalesBudgetCellOut]
    month_totals: dict[int, float]
    grand_total: float


class SalesBudgetCellIn(BaseModel):
    customer_id: int
    product_id: int
    month: int = Field(ge=1, le=12)
    currency: str = "TWD"
    quantity: float
    amount: float


class SalesBudgetSaveRequest(BaseModel):
    version_id: int
    salesperson_id: int
    cells: list[SalesBudgetCellIn]
    notes: dict[str, str | None] = Field(default_factory=dict)  # key: "customer_id-product_id"


class SalesBudgetSyncResult(BaseModel):
    accounts_updated: int
    cells_updated: int
    grand_total: float


# --------------------------------------------------------------------------- #
# 資產類別主檔
# --------------------------------------------------------------------------- #
class AssetCategoryBase(BaseModel):
    code: str = Field(max_length=20)
    name: str = Field(max_length=100)
    depreciation_months: int = 60
    asset_account_id: int | None = None
    expense_account_id: int | None = None
    is_active: bool = True


class AssetCategoryCreate(AssetCategoryBase):
    pass


class AssetCategoryUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    depreciation_months: int | None = None
    asset_account_id: int | None = None
    expense_account_id: int | None = None
    is_active: bool | None = None


class AssetCategoryOut(ORMModel, AssetCategoryBase):
    id: int
    asset_account_code: str | None = None
    expense_account_code: str | None = None


# --------------------------------------------------------------------------- #
# 資本支出項目(新增即成為既有資產,往後年度自動攤提折舊)
# --------------------------------------------------------------------------- #
class CapexItemBase(BaseModel):
    department_id: int
    asset_category_id: int
    name: str = Field(max_length=150)
    acquisition_cost: float = 0
    acquisition_yyyymm: int = Field(ge=190001, le=999912)
    depreciation_start_yyyymm: int | None = None  # 未填則預設等於購置年月
    depreciation_months: int | None = None  # 未填則沿用資產類別預設值
    justification: str | None = None


class CapexItemCreate(CapexItemBase):
    version_id: int


class CapexItemUpdate(BaseModel):
    name: str | None = None
    asset_category_id: int | None = None
    acquisition_cost: float | None = None
    acquisition_yyyymm: int | None = Field(default=None, ge=190001, le=999912)
    depreciation_start_yyyymm: int | None = None
    depreciation_months: int | None = None
    justification: str | None = None


class CapexItemOut(ORMModel, CapexItemBase):
    id: int
    version_id: int
    status: CapexStatus
    department_name: str | None = None
    asset_category_name: str | None = None
    expense_account_id: int | None = None
    expense_account_code: str | None = None
    expense_account_name: str | None = None
    monthly_depreciation: float = 0
    created_at: datetime
    updated_at: datetime


class CapexSyncResult(BaseModel):
    accounts_updated: int
    grand_total: float


# --------------------------------------------------------------------------- #
# 費用預算(格式化收集表)
# --------------------------------------------------------------------------- #
class ExpenseFormatColumnIn(BaseModel):
    key: str = Field(max_length=50)
    label: str = Field(max_length=100)
    sort_order: int = 0


class ExpenseFormatAccountMapIn(BaseModel):
    function: ExpenseFunction
    account_id: int


class ExpenseFormatCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=100)
    sort_order: int = 0
    columns: list[ExpenseFormatColumnIn] = Field(default_factory=list)
    account_maps: list[ExpenseFormatAccountMapIn] = Field(default_factory=list)


class ExpenseFormatUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    columns: list[ExpenseFormatColumnIn] | None = None
    account_maps: list[ExpenseFormatAccountMapIn] | None = None


class ExpenseFormatColumnOut(BaseModel):
    id: int
    key: str
    label: str
    sort_order: int


class ExpenseFormatAccountMapOut(BaseModel):
    function: ExpenseFunction
    account_id: int
    account_code: str | None = None
    account_name: str | None = None


class ExpenseFormatOut(BaseModel):
    id: int
    code: str
    name: str
    sort_order: int
    is_active: bool
    columns: list[ExpenseFormatColumnOut]
    account_maps: list[ExpenseFormatAccountMapOut]


class ExpenseGridCellOut(BaseModel):
    column_key: str
    column_label: str
    months: dict[int, float]
    total: float


class ExpenseGridResponse(BaseModel):
    version: VersionOut
    department: DepartmentOut
    format: ExpenseFormatOut
    editable: bool
    rows: list[ExpenseGridCellOut]
    month_totals: dict[int, float]
    grand_total: float
    resolved_account: ExpenseFormatAccountMapOut | None = None


class ExpenseCellIn(BaseModel):
    column_key: str
    month: int = Field(ge=1, le=12)
    amount: float


class ExpenseSaveRequest(BaseModel):
    version_id: int
    department_id: int
    format_id: int
    cells: list[ExpenseCellIn]


class ExpenseSyncResult(BaseModel):
    accounts_updated: int
    grand_total: float


# --------------------------------------------------------------------------- #
# 權限授予(人 × 模組 × 部門 / 銷售人員 / 費用格式)
# --------------------------------------------------------------------------- #
class AccessGrantCreate(BaseModel):
    user_id: int
    module: GrantModule
    department_id: int
    salesperson_id: int | None = None
    expense_format_id: int | None = None


class AccessGrantOut(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    module: GrantModule
    department_id: int
    department_name: str | None = None
    salesperson_id: int | None = None
    salesperson_name: str | None = None
    expense_format_id: int | None = None
    expense_format_name: str | None = None
    created_at: datetime
