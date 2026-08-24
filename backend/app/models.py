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


# --------------------------------------------------------------------------- #
# 主檔
# --------------------------------------------------------------------------- #
class Department(Base):
    """部門 / 成本中心。以 parent_id 自我參照構成多層組織樹。"""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[DeptKind] = mapped_column(Enum(DeptKind), default=DeptKind.department)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    manager: Mapped[str | None] = mapped_column(String(50))
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
