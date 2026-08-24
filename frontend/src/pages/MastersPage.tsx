import { useState } from "react";
import DepartmentsTab from "./masters/DepartmentsTab";
import AccountsTab from "./masters/AccountsTab";
import VersionsTab from "./masters/VersionsTab";
import ActualsTab from "./masters/ActualsTab";

type Tab = "departments" | "accounts" | "versions" | "actuals";

const TABS: { key: Tab; label: string }[] = [
  { key: "departments", label: "部門 / 成本中心" },
  { key: "accounts", label: "會計科目" },
  { key: "versions", label: "預算版本" },
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
      {tab === "actuals" && <ActualsTab />}
    </div>
  );
}
