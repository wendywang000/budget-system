export type UserRole = "finance_admin" | "dept_user";
export type DeptKind = "company" | "division" | "department" | "cost_center" | "project";
export type AccountCategory = "revenue" | "cost" | "expense" | "capex";
export type VersionStatus = "draft" | "open" | "locked";
export type SubmissionStatus = "draft" | "submitted" | "returned" | "approved";
export type ExpenseFunction = "sales" | "admin" | "rd" | "manufacturing";
export type GrantModule = "budget" | "sales" | "expense" | "capex" | "report";

export const FUNCTION_LABELS: Record<ExpenseFunction, string> = {
  sales: "銷",
  admin: "管",
  rd: "研",
  manufacturing: "製",
};

export const MODULE_LABELS: Record<GrantModule, string> = {
  budget: "科目預算表",
  sales: "銷售量預算",
  expense: "費用預算",
  capex: "資本支出",
  report: "報表查詢",
};

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
  name_zh_hans: string | null;
  name_en: string | null;
  kind: DeptKind;
  parent_id: number | null;
  manager: string | null;
  function: ExpenseFunction | null;
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

export interface Product {
  id: number;
  code: string;
  name: string;
  category: string | null;
  unit: string;
  unit_price: number;
  unit_cost: number;
  revenue_account_id: number | null;
  is_active: boolean;
}

export interface Customer {
  id: number;
  code: string;
  name: string;
  region: string | null;
  sales_rep: string | null;
  is_active: boolean;
}

export interface Salesperson {
  id: number;
  code: string;
  name: string;
  department_id: number;
  department_name: string | null;
  is_active: boolean;
}

export interface SalesBudgetMonthCell {
  quantity: number;
  amount: number;
}

export interface SalesBudgetCellOut {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  product_id: number;
  product_code: string;
  product_name: string;
  unit: string;
  currency: string;
  months: Record<number, SalesBudgetMonthCell>;
  total_quantity: number;
  total_amount: number;
  note: string | null;
}

export interface SalesBudgetGridResponse {
  version: BudgetVersion;
  department: Department | null;
  salesperson: Salesperson;
  editable: boolean;
  rows: SalesBudgetCellOut[];
  month_totals: Record<number, number>;
  grand_total: number;
}

export type CapexStatus = "draft" | "submitted" | "returned" | "approved";

export const CAPEX_STATUS_LABELS: Record<CapexStatus, string> = {
  draft: "編列中",
  submitted: "已送出",
  returned: "已退回",
  approved: "已核定",
};

export interface AssetCategory {
  id: number;
  code: string;
  name: string;
  depreciation_months: number;
  asset_account_id: number | null;
  expense_account_id: number | null;
  asset_account_code: string | null;
  expense_account_code: string | null;
  is_active: boolean;
}

export interface CapexItem {
  id: number;
  version_id: number;
  department_id: number;
  department_name: string | null;
  asset_category_id: number;
  asset_category_name: string | null;
  name: string;
  acquisition_cost: number;
  acquisition_yyyymm: number;
  depreciation_start_yyyymm: number | null;
  depreciation_months: number | null;
  justification: string | null;
  status: CapexStatus;
  expense_account_id: number | null;
  expense_account_code: string | null;
  expense_account_name: string | null;
  monthly_depreciation: number;
  created_at: string;
  updated_at: string;
}

export interface ExpenseFormatColumn {
  id: number;
  key: string;
  label: string;
  sort_order: number;
}

export interface ExpenseFormatAccountMap {
  function: ExpenseFunction;
  account_id: number;
  account_code: string | null;
  account_name: string | null;
}

export interface ExpenseFormat {
  id: number;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  columns: ExpenseFormatColumn[];
  account_maps: ExpenseFormatAccountMap[];
}

export interface ExpenseGridCell {
  column_key: string;
  column_label: string;
  months: Record<number, number>;
  total: number;
}

export interface ExpenseGridResponse {
  version: BudgetVersion;
  department: Department;
  format: ExpenseFormat;
  editable: boolean;
  rows: ExpenseGridCell[];
  month_totals: Record<number, number>;
  grand_total: number;
  resolved_account: ExpenseFormatAccountMap | null;
}

export interface AccessGrant {
  id: number;
  user_id: number;
  user_name: string | null;
  module: GrantModule;
  department_id: number;
  department_name: string | null;
  salesperson_id: number | null;
  salesperson_name: string | null;
  expense_format_id: number | null;
  expense_format_name: string | null;
  created_at: string;
}
