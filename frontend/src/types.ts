export type UserRole = "finance_admin" | "dept_user";
export type DeptKind = "company" | "division" | "department" | "cost_center" | "project";
export type AccountCategory = "revenue" | "cost" | "expense" | "capex";
export type VersionStatus = "draft" | "open" | "locked";
export type SubmissionStatus = "draft" | "submitted" | "returned" | "approved";

export const CATEGORY_LABELS: Record<AccountCategory, string> = {
  revenue: "營業收入",
  cost: "營業成本",
  expense: "營業費用",
  capex: "資本支出",
};

export const VERSION_STATUS_LABELS: Record<VersionStatus, string> = {
  draft: "草擬中",
  open: "開放填報",
  locked: "已鎖定",
};

export const SUBMISSION_STATUS_LABELS: Record<SubmissionStatus, string> = {
  draft: "編列中",
  submitted: "已送出",
  returned: "已退回",
  approved: "已核定",
};

export const DEPT_KIND_LABELS: Record<DeptKind, string> = {
  company: "公司",
  division: "事業處",
  department: "部門",
  cost_center: "成本中心",
  project: "專案",
};

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  department_id: number | null;
  department_name: string | null;
  is_active: boolean;
}

export interface Department {
  id: number;
  code: string;
  name: string;
  kind: DeptKind;
  parent_id: number | null;
  manager: string | null;
  sort_order: number;
  is_active: boolean;
  level: number;
  has_children: boolean;
}

export interface Account {
  id: number;
  code: string;
  name: string;
  category: AccountCategory;
  parent_id: number | null;
  is_postable: boolean;
  sort_order: number;
  is_active: boolean;
  note: string | null;
  level: number;
  has_children: boolean;
}

export interface BudgetVersion {
  id: number;
  fiscal_year: number;
  name: string;
  status: VersionStatus;
  is_default: boolean;
  description: string | null;
  created_at: string;
}

export interface GridRow {
  account_id: number;
  account_code: string;
  account_name: string;
  category: AccountCategory;
  level: number;
  is_postable: boolean;
  months: Record<number, number>;
  total: number;
  note: string | null;
}

export interface GridResponse {
  version: BudgetVersion;
  department: Department;
  editable: boolean;
  submission_status: SubmissionStatus;
  submission_comment: string | null;
  rows: GridRow[];
  month_totals: Record<number, number>;
  grand_total: number;
  category_totals: Record<string, number>;
}

export interface SubmissionOut {
  id: number | null;
  version_id: number;
  department_id: number;
  department_code: string | null;
  department_name: string | null;
  status: SubmissionStatus;
  comment: string | null;
  total: number;
  submitted_at: string | null;
  reviewed_at: string | null;
}

export interface SummaryRow {
  key: string;
  code: string;
  name: string;
  level: number;
  category: string | null;
  months: Record<number, number>;
  total: number;
  is_group: boolean;
}

export interface SummaryResponse {
  version: BudgetVersion;
  group_by: "account" | "department";
  rows: SummaryRow[];
  month_totals: Record<number, number>;
  grand_total: number;
}

export interface VarianceRow {
  key: string;
  code: string;
  name: string;
  level: number;
  category: string | null;
  is_group: boolean;
  budget: number;
  actual: number;
  variance: number;
  achievement: number | null;
  budget_ytd: number;
  actual_ytd: number;
  variance_ytd: number;
}

export interface VarianceResponse {
  fiscal_year: number;
  version: BudgetVersion;
  through_month: number;
  group_by: "account" | "department";
  rows: VarianceRow[];
  totals: VarianceRow;
}

export interface ImportResult {
  inserted: number;
  updated: number;
  skipped: number;
  errors: string[];
}
