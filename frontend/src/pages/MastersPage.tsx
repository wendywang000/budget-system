import { useState } from "react";
import DepartmentsTab from "./masters/DepartmentsTab";
import AccountsTab from "./masters/AccountsTab";
import VersionsTab from "./masters/VersionsTab";
import ActualsTab from "./masters/ActualsTab";
import ProductsTab from "./masters/ProductsTab";
import CustomersTab from "./masters/CustomersTab";
import SalespeopleTab from "./masters/SalespeopleTab";
import AssetCategoriesTab from "./masters/AssetCategoriesTab";
import ExpenseFormatsTab from "./masters/ExpenseFormatsTab";
import AccessGrantsTab from "./masters/AccessGrantsTab";

type Tab =
  | "departments"
  | "accounts"
  | "versions"
  | "products"
  | "customers"
  | "salespeople"
  | "asset_categories"
  | "expense_formats"
  | "access_grants"
  | "actuals";

const TABS: { key: Tab; label: string }[] = [
  { key: "departments", label: "部門 / 成本中心" },
  { key: "accounts", label: "會計科目" },
  { key: "versions", label: "預算版本" },
  { key: "products", label: "產品資料" },
  { key: "customers", label: "客戶名單" },
  { key: "salespeople", label: "銷售人員" },
  { key: "asset_categories", label: "資產類別" },
  { key: "expense_formats", label: "費用格式" },
  { key: "access_grants", label: "權限授予" },
  { key: "actuals", label: "實際數匯入" },
];

export default function MastersPage() {
  const [tab, setTab] = useState<Tab>("departments");

  return (
    <div className="page">
      <div className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "tab-button active" : "tab-button"}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "departments" && <DepartmentsTab />}
      {tab === "accounts" && <AccountsTab />}
      {tab === "versions" && <VersionsTab />}
      {tab === "products" && <ProductsTab />}
      {tab === "customers" && <CustomersTab />}
      {tab === "salespeople" && <SalespeopleTab />}
      {tab === "asset_categories" && <AssetCategoriesTab />}
      {tab === "expense_formats" && <ExpenseFormatsTab />}
      {tab === "access_grants" && <AccessGrantsTab />}
      {tab === "actuals" && <ActualsTab />}
    </div>
  );
}
