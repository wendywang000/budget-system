import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Account, AssetCategory, ImportResult } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  depreciation_months: 60,
  asset_account_id: "" as number | "",
  expense_account_id: "" as number | "",
  is_active: true,
};

export default function AssetCategoriesTab() {
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const [cRes, aRes] = await Promise.all([
        api.get<AssetCategory[]>("/asset-categories", { params: { active_only: false } }),
        api.get<Account[]>("/accounts", { params: { active_only: true } }),
      ]);
      setCategories(cRes.data);
      setAccounts(aRes.data.filter((a) => !a.has_children));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(cat: AssetCategory) {
    setForm({
      id: cat.id,
      code: cat.code,
      name: cat.name,
      depreciation_months: cat.depreciation_months,
      asset_account_id: cat.asset_account_id ?? "",
      expense_account_id: cat.expense_account_id ?? "",
      is_active: cat.is_active,
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const payload = {
      code: form.code,
      name: form.name,
      depreciation_months: form.depreciation_months,
      asset_account_id: form.asset_account_id === "" ? null : Number(form.asset_account_id),
      expense_account_id: form.expense_account_id === "" ? null : Number(form.expense_account_id),
      is_active: form.is_active,
    };
    try {
      if (form.id === null) {
        await api.post("/asset-categories", payload);
        setMessage("已新增資產類別");
      } else {
        await api.patch(`/asset-categories/${form.id}`, payload);
        setMessage("已更新資產類別");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(cat: AssetCategory) {
    if (!window.confirm(`確定要刪除資產類別「${cat.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/asset-categories/${cat.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    setError(null);
    try {
      const res = await api.get("/excel/asset-categories/template", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "asset_categories_template.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/asset-categories/export", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "asset_categories.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleImport(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post<ImportResult>("/excel/asset-categories/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const r = res.data;
      setMessage(`匯入完成:新增 ${r.inserted}、更新 ${r.updated}${r.deactivated ? `、停用 ${r.deactivated}` : ""}、略過 ${r.skipped}。`);
      if (r.errors.length) setError(r.errors.join("\n"));
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="masters-tab">
      <div className="page-toolbar">
        <span className="hint-text">可匯入資產類別資料，支援攤銷月數與資產/費用科目對應</span>
        <div className="toolbar-spacer" />
        <button type="button" onClick={handleTemplate} disabled={busy}>下載範本</button>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={busy}>{busy ? "處理中…" : "匯入 Excel"}</button>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={handleImport} />
        <button type="button" onClick={handleExport} disabled={busy}>匯出 Excel</button>
      </div>
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增資產類別" : `編輯資產類別 #${form.id}`}</h3>
        <p className="hint-text">
          資本支出編列時選擇資產類別,即可帶入預設攤銷月數與資產/費用科目;攤銷月數 0 表示不攤銷(如土地)。
        </p>
        <div className="form-grid">
          <label>
            代號
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
          </label>
          <label>
            名稱
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            攤銷月數
            <input
              type="number"
              value={form.depreciation_months}
              onChange={(e) => setForm({ ...form, depreciation_months: Number(e.target.value) })}
            />
          </label>
          <label>
            資產科目
            <select
              value={form.asset_account_id}
              onChange={(e) => setForm({ ...form, asset_account_id: e.target.value ? Number(e.target.value) : "" })}
            >
              <option value="">（不設定）</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} {a.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            費用科目(折舊)
            <select
              value={form.expense_account_id}
              onChange={(e) =>
                setForm({ ...form, expense_account_id: e.target.value ? Number(e.target.value) : "" })
              }
            >
              <option value="">（不設定）</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            啟用
          </label>
        </div>
        <div className="form-actions">
          <button type="submit">{form.id === null ? "新增" : "儲存"}</button>
          {form.id !== null && (
            <button type="button" onClick={() => setForm(emptyForm)}>
              取消編輯
            </button>
          )}
        </div>
      </form>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}
      {loading ? (
        <div className="page-loading">載入中…</div>
      ) : (
        <table className="plain-table">
          <thead>
            <tr>
              <th>代號</th>
              <th>名稱</th>
              <th>攤銷月數</th>
              <th>資產科目</th>
              <th>費用科目</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.id} className={c.is_active ? "" : "inactive-row"}>
                <td>{c.code}</td>
                <td>{c.name}</td>
                <td>{c.depreciation_months || "不攤銷"}</td>
                <td>{c.asset_account_code ?? ""}</td>
                <td>{c.expense_account_code ?? ""}</td>
                <td>{c.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(c)}>編輯</button>
                  <button onClick={() => handleDelete(c)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
