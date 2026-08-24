from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    AccountCategory,
    DeptKind,
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
    kind: DeptKind = DeptKind.department
    parent_id: int | None = None
    manager: str | None = None
    sort_order: int = 0
    is_active: bool = True


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    kind: DeptKind | None = None
    parent_id: int | None = None
    manager: str | None = None
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
