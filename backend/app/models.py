from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# 列舉
# --------------------------------------------------------------------------- #
class UserRole(str, enum.Enum):
    """finance_admin 可看全公司並鎖定版本;dept_user 只能編自己部門(含子部門)。"""

    finance_admin = "finance_admin"
    dept_user = "dept_user"


class DeptKind(str, enum.Enum):
    company = "company"          # 公司
    division = "division"        # 中心 / 事業處
    department = "department"    # 部門
    cost_center = "cost_center"  # 成本中心 / 課
    project = "project"          # 專案


class AccountCategory(str, enum.Enum):
    revenue = "revenue"  # 營業收入
    cost = "cost"        # 營業成本
    expense = "expense"  # 營業費用
    capex = "capex"      # 資本支出


class VersionStatus(str, enum.Enum):
    draft = "draft"    # 草擬中(尚未開放填報)
    open = "open"      # 開放填報
    locked = "locked"  # 已鎖定(只能檢視)


class SubmissionStatus(str, enum.Enum):
    draft = "draft"          # 部門編列中
    submitted = "submitted"  # 部門已送出
    returned = "returned"    # 財務退回
    approved = "approved"    # 財務核定


class CapexStatus(str, enum.Enum):
    draft = "draft"          # 編列中
    submitted = "submitted"  # 已送出
    returned = "returned"    # 財務退回
    approved = "approved"    # 財務核定


class GrantModule(str, enum.Enum):
    """權限授予的模組範圍。同一人可在不同模組被授予不同部門的存取權。"""

    budget = "budget"    # 科目預算表(填報/送出/核定)
    sales = "sales"      # 銷售量預算
    expense = "expense"  # 費用預算(格式化收集表)
    capex = "capex"      # 資本支出編列
    report = "report"    # 報表查詢(唯讀,彙總/差異分析)


class ExpenseFunction(str, enum.Enum):
    """費用項目對應會計科目時的作業功能別,同一費用項目在不同功能別可能對應不同科目。"""

    sales = "sales"                # 銷
    admin = "admin"                # 管
    rd = "rd"                      # 研
    manufacturing = "manufacturing"  # 製


# --------------------------------------------------------------------------- #
# 主檔
# --------------------------------------------------------------------------- #
class Department(Base):
    """部門 / 成本中心。以 parent_id 自我參照構成多層組織樹。"""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    name_zh_hans: Mapped[str | None] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[DeptKind] = mapped_column(Enum(DeptKind), default=DeptKind.department)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    manager: Mapped[str | None] = mapped_column(String(50))
    function: Mapped[ExpenseFunction | None] = mapped_column(Enum(ExpenseFunction))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped[Department | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[Department]] = relationship(back_populates="parent")


class Account(Base):
    """會計科目。父科目僅作分組表頭,實際金額只掛在 is_postable 的葉科目上。"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[AccountCategory] = mapped_column(Enum(AccountCategory))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    is_postable: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(200))

    parent: Mapped[Account | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[Account]] = relationship(back_populates="parent")


class AssetCategory(Base):
    """資產類別主檔:決定新增資本支出項目預設的攤銷月數與資產/費用科目。"""

    __tablename__ = "asset_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    depreciation_months: Mapped[int] = mapped_column(Integer, default=60)
    asset_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    expense_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    asset_account: Mapped[Account | None] = relationship(foreign_keys=[asset_account_id])
    expense_account: Mapped[Account | None] = relationship(foreign_keys=[expense_account_id])


class Product(Base):
    """產品主檔,供銷售量預算引用。"""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(50))
    unit: Mapped[str] = mapped_column(String(20), default="PCS")
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    revenue_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    revenue_account: Mapped[Account | None] = relationship()


class Customer(Base):
    """客戶主檔,供銷售量預算引用。"""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    region: Mapped[str | None] = mapped_column(String(50))
    sales_rep: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Salesperson(Base):
    """銷售人員主檔。銷售量預算以銷售人員填報,再依 department_id 滾算至其所屬預算單位。"""

    __tablename__ = "salespeople"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    department: Mapped[Department] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.dept_user)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    department: Mapped[Department | None] = relationship()


class AccessGrant(Base):
    """人 × 模組 × 部門(可選:銷售人員 / 費用格式)的細粒度資料存取授權。

    dept_user 預設仍可透過 User.department_id 存取自己部門(budget 模組)的資料;
    AccessGrant 用來額外授予其他部門,或授予銷售量預算 / 費用預算 / 資本支出 / 報表查詢等模組的權限,
    可與其他部門的同類授權疊加,不會互相取代。
    """

    __tablename__ = "access_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "module", "department_id", "salesperson_id", "expense_format_id",
            name="uq_access_grant",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    module: Mapped[GrantModule] = mapped_column(Enum(GrantModule), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    salesperson_id: Mapped[int | None] = mapped_column(ForeignKey("salespeople.id"))
    expense_format_id: Mapped[int | None] = mapped_column(ForeignKey("expense_formats.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# --------------------------------------------------------------------------- #
# 預算
# --------------------------------------------------------------------------- #
class BudgetVersion(Base):
    """一個年度可以有多個版本(初版 / 修正版 / 樂觀情境…),互不干擾。"""

    __tablename__ = "budget_versions"
    __table_args__ = (UniqueConstraint("fiscal_year", "name", name="uq_version_year_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60))
    status: Mapped[VersionStatus] = mapped_column(Enum(VersionStatus), default=VersionStatus.open)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BudgetEntry(Base):
    """預算明細:一格 = 版本 × 部門 × 科目 × 月份。"""

    __tablename__ = "budget_entries"
    __table_args__ = (
        UniqueConstraint("version_id", "department_id", "account_id", "month", name="uq_budget_cell"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    month: Mapped[int] = mapped_column(Integer)  # 1..12
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Submission(Base):
    """部門填報狀態:版本 × 部門一筆。"""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("version_id", "department_id", name="uq_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus), default=SubmissionStatus.draft)
    comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Actual(Base):
    """實際數:年度 × 部門 × 科目 × 月份。由 Excel 或 ERP 匯入。"""

    __tablename__ = "actuals"
    __table_args__ = (
        UniqueConstraint("fiscal_year", "department_id", "account_id", "month", name="uq_actual_cell"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    month: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SalesBudgetEntry(Base):
    """銷售量預算明細:版本 × 銷售人員 × 客戶 × 產品 × 幣別 × 月份,直接填數量與交易金額。

    department_id 於儲存時由 Salesperson.department_id 帶入(銷售人員所屬預算單位),
    僅作查詢/權限過濾用,不可獨立指定。
    可用「同步至預算表」把彙總金額寫回該產品對應收入科目的 BudgetEntry。
    """

    __tablename__ = "sales_budget_entries"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "salesperson_id", "customer_id", "product_id", "month",
            name="uq_sales_budget_cell",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    salesperson_id: Mapped[int] = mapped_column(ForeignKey("salespeople.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    month: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(6), default="TWD")
    quantity: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CapexItem(Base):
    """資本支出項目(資產登記):版本(提出年度)× 部門 × 資產類別,一經核定即成為「既有資產」,

    往後每個預算年度都會依攤銷月數自動算出應攤提的折舊費用(同步進該資產類別對應的費用科目),
    不需每年重新輸入 —— 對應舊系統「新增資本支出」+「既有資本支出折舊」兩張表的合併設計。
    """

    __tablename__ = "capex_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id"), index=True)  # 提出/建立的預算版本
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    asset_category_id: Mapped[int] = mapped_column(ForeignKey("asset_categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    acquisition_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    acquisition_yyyymm: Mapped[int] = mapped_column(Integer)  # 購置年月,例如 202609
    depreciation_start_yyyymm: Mapped[int] = mapped_column(Integer)  # 攤銷起始年月
    depreciation_months: Mapped[int] = mapped_column(Integer, default=0)  # 0 表示不攤銷(如土地)
    justification: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CapexStatus] = mapped_column(Enum(CapexStatus), default=CapexStatus.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# --------------------------------------------------------------------------- #
# 費用預算(格式化收集表)
# --------------------------------------------------------------------------- #
class ExpenseFormat(Base):
    """費用收集格式主檔,例如「直接用人費」「間接材料」「旅費-國內」等,每種格式有自己的欄位組合。"""

    __tablename__ = "expense_formats"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    columns: Mapped[list[ExpenseFormatColumn]] = relationship(
        back_populates="format", order_by="ExpenseFormatColumn.sort_order", cascade="all, delete-orphan"
    )
    account_maps: Mapped[list[ExpenseFormatAccountMap]] = relationship(
        back_populates="format", cascade="all, delete-orphan"
    )


class ExpenseFormatColumn(Base):
    """費用格式底下的欄位定義,例如「薪資」「加班費」「勞保公司負擔」…,同格式各欄位金額加總後才對應到科目。"""

    __tablename__ = "expense_format_columns"
    __table_args__ = (UniqueConstraint("format_id", "key", name="uq_expense_format_column"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    format_id: Mapped[int] = mapped_column(ForeignKey("expense_formats.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    format: Mapped[ExpenseFormat] = relationship(back_populates="columns")


class ExpenseFormatAccountMap(Base):
    """費用格式 × 作業功能別(銷/管/研/製)→ 會計科目 的對應表。"""

    __tablename__ = "expense_format_account_maps"
    __table_args__ = (
        UniqueConstraint("format_id", "function", name="uq_expense_format_function"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    format_id: Mapped[int] = mapped_column(ForeignKey("expense_formats.id", ondelete="CASCADE"), index=True)
    function: Mapped[ExpenseFunction] = mapped_column(Enum(ExpenseFunction))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    format: Mapped[ExpenseFormat] = relationship(back_populates="account_maps")
    account: Mapped[Account] = relationship()


class ExpenseEntry(Base):
    """費用預算明細:版本 × 部門 × 費用格式 × 欄位 × 月份 一格金額。"""

    __tablename__ = "expense_entries"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "department_id", "format_id", "column_key", "month",
            name="uq_expense_cell",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_versions.id", ondelete="CASCADE"), index=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    format_id: Mapped[int] = mapped_column(ForeignKey("expense_formats.id"), index=True)
    column_key: Mapped[str] = mapped_column(String(50))
    month: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
