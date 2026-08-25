import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { AssetCategory, CapexItem } from "../types";
import { CAPEX_STATUS_LABELS } from "../types";
import { formatNumber } from "../utils/format";

const emptyForm = {
  asset_category_id: "" as number | "",
  name: "",
  acquisition_cost: 0,
  acquisition_yyyymm: "",
  depreciation_months: "" as number | "",
  justification: "",
};

export default function CapexPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "finance_admin";
  const { versions, departments, loading: refLoading } = useVersionsAndDepartments(true);
  const [assetCategories, setAssetCategories] = useState<AssetCategory[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [items, setItems] = useState<CapexItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  useEffect(() => {
    api
      .get<AssetCategory[]>("/asset-categories")
      .then((res) => setAssetCategories(res.data))
      .catch((err) => setError(apiErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      setVersionId((versions.find((v) => v.is_default) ?? versions[0]).id);
    }
  }, [versions, versionId]);

  useEffect(() => {
    if (departmentId === null && departments.length > 0) {
      setDepartmentId(departments[0].id);
    }
  }, [departments, departmentId]);

  async function load() {
    if (versionId === null || departmentId === null) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<CapexItem[]>("/capex", {
        params: { version_id: versionId, department_id: departmentId, include_prior_vintages: true },
      });
      setItems(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, departmentId]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (versionId === null || departmentId === null || form.asset_category_id === "" || !form.acquisition_yyyymm) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await api.post("/capex", {
        version_id: versionId,
        department_id: departmentId,
        asset_category_id: Number(form.asset_category_id),
        name: form.name,
        acquisition_cost: form.acquisition_cost,
        acquisition_yyyymm: Number(form.acquisition_yyyymm),
        depreciation_months: form.depreciation_months === "" ? null : Number(form.depreciation_months),
        justification: form.justification || null,
      });
      setMessage("已新增資本支出項目");
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function act(item: CapexItem, action: "submit" | "approve" | "return") {
    setError(null);
    setMessage(null);
    try {
      await api.post(`/capex/${item.id}/${action}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(item: CapexItem) {
    if (!window.confirm(`確定要刪除「${item.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/capex/${item.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleSync() {
    if (versionId === null || departmentId === null) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.post("/capex/sync", null, { params: { version_id: versionId, department_id: departmentId } });
      setMessage(`已同步至費用科目:更新 ${res.data.accounts_updated} 個科目,合計 ${formatNumber(res.data.grand_total)}。`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const currentVersionItems = items.filter((i) => i.version_id === versionId);
  const priorVintageItems = items.filter((i) => i.version_id !== versionId);
  const totalCost = items.reduce((sum, i) => sum + i.acquisition_cost, 0);
  const totalMonthlyDepreciation = items.reduce((sum, i) => sum + i.monthly_depreciation, 0);

  if (refLoading) return <div className="page-loading">載入中…</div>;

  return (
    <div className="page">
      <div className="page-toolbar">
        <label>
          預算版本
          <select value={versionId ?? ""} onChange={(e) => setVersionId(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.fiscal_year} - {v.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          部門
          <select value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {"　".repeat(d.level)}
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <div className="toolbar-spacer" />
        <button onClick={handleSync} disabled={saving}>
          同步本年度折舊至費用科目
        </button>
      </div>

      <form className="masters-form" onSubmit={handleCreate}>
        <h3>新增資本支出項目</h3>
        <div className="form-grid">
          <label>
            資產類別
            <select
              value={form.asset_category_id}
              onChange={(e) => setForm({ ...form, asset_category_id: e.target.value ? Number(e.target.value) : "" })}
              required
            >
              <option value="">請選擇</option>
              {assetCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} {c.name}（攤銷 {c.depreciation_months || "不攤銷"} 月）
                </option>
              ))}
            </select>
          </label>
          <label>
            項目名稱
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            購置成本
            <input
              type="number"
              value={form.acquisition_cost}
              onChange={(e) => setForm({ ...form, acquisition_cost: Number(e.target.value) })}
            />
          </label>
          <label>
            購置年月(YYYYMM)
            <input
              placeholder="例如 202706"
              value={form.acquisition_yyyymm}
              onChange={(e) => setForm({ ...form, acquisition_yyyymm: e.target.value })}
              required
            />
          </label>
          <label>
            攤銷月數(留白＝沿用類別預設)
            <input
              type="number"
              value={form.depreciation_months}
              onChange={(e) => setForm({ ...form, depreciation_months: e.target.value ? Number(e.target.value) : "" })}
            />
          </label>
          <label className="wide-field">
            說明
            <input value={form.justification} onChange={(e) => setForm({ ...form, justification: e.target.value })} />
          </label>
        </div>
        <div className="form-actions">
          <button type="submit" disabled={saving}>
            新增
          </button>
        </div>
      </form>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}
      {loading ? (
        <div className="page-loading">載入中…</div>
      ) : (
        <>
          <h4>本版本新提出項目</h4>
          <CapexTable items={currentVersionItems} isAdmin={isAdmin} onAct={act} onDelete={handleDelete} />

          <h4>既有資產(過去核定、本年度仍在攤銷期間內)</h4>
          <CapexTable items={priorVintageItems} isAdmin={isAdmin} onAct={act} onDelete={handleDelete} readOnly />

          <div className="grid-meta">
            <span>合計購置成本:{formatNumber(totalCost)}</span>
            <span>本年度每月折舊約:{formatNumber(totalMonthlyDepreciation)}</span>
          </div>
        </>
      )}
    </div>
  );
}

function CapexTable({
  items,
  isAdmin,
  onAct,
  onDelete,
  readOnly,
}: {
  items: CapexItem[];
  isAdmin: boolean;
  onAct: (item: CapexItem, action: "submit" | "approve" | "return") => void;
  onDelete: (item: CapexItem) => void;
  readOnly?: boolean;
}) {
  if (items.length === 0) return <p className="hint-text">（無資料）</p>;
  return (
    <div className="table-scroll">
      <table className="plain-table">
        <thead>
          <tr>
            <th>資產類別</th>
            <th>項目名稱</th>
            <th>購置成本</th>
            <th>購置年月</th>
            <th>攤銷月數</th>
            <th>每月折舊</th>
            <th>費用科目</th>
            <th>狀態</th>
            {!readOnly && <th>操作</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>{item.asset_category_name}</td>
              <td>{item.name}</td>
              <td className="col-number">{formatNumber(item.acquisition_cost)}</td>
              <td>{item.acquisition_yyyymm}</td>
              <td>{item.depreciation_months || "不攤銷"}</td>
              <td className="col-number">{formatNumber(item.monthly_depreciation)}</td>
              <td>{item.expense_account_code}</td>
              <td>
                <span className={`status-pill status-${item.status}`}>{CAPEX_STATUS_LABELS[item.status]}</span>
              </td>
              {!readOnly && (
                <td className="action-cell">
                  {item.status === "draft" && <button onClick={() => onAct(item, "submit")}>送出</button>}
                  {isAdmin && item.status === "submitted" && (
                    <>
                      <button onClick={() => onAct(item, "approve")}>核定</button>
                      <button onClick={() => onAct(item, "return")}>退回</button>
                    </>
                  )}
                  {item.status !== "approved" && <button onClick={() => onDelete(item)}>刪除</button>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
