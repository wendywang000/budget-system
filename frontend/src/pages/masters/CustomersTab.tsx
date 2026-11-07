import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Customer, ImportResult } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  region: "",
  sales_rep: "",
  is_active: true,
};

export default function CustomersTab() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<Customer[]>("/customers", { params: { active_only: false } });
      setCustomers(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(customer: Customer) {
    setForm({
      id: customer.id,
      code: customer.code,
      name: customer.name,
      region: customer.region ?? "",
      sales_rep: customer.sales_rep ?? "",
      is_active: customer.is_active,
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const payload = {
      code: form.code,
      name: form.name,
      region: form.region || null,
      sales_rep: form.sales_rep || null,
      is_active: form.is_active,
    };
    try {
      if (form.id === null) {
        await api.post("/customers", payload);
        setMessage("已新增客戶");
      } else {
        await api.patch(`/customers/${form.id}`, payload);
        setMessage("已更新客戶");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(customer: Customer) {
    if (!window.confirm(`確定要刪除客戶「${customer.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/customers/${customer.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    setError(null);
    try {
      const res = await api.get("/excel/customers/template", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "customers_template.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/customers/export", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "customers.xlsx"));
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
      const res = await api.post<ImportResult>("/excel/customers/import", formData, {
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
        <span className="hint-text">可匯入客戶名單，支援代碼、名稱、區域與業務負責人資料</span>
        <div className="toolbar-spacer" />
        <button type="button" onClick={handleTemplate} disabled={busy}>下載範本</button>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={busy}>{busy ? "處理中…" : "匯入 Excel"}</button>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={handleImport} />
        <button type="button" onClick={handleExport} disabled={busy}>匯出 Excel</button>
      </div>
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增客戶" : `編輯客戶 #${form.id}`}</h3>
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
            區域
            <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
          </label>
          <label>
            業務負責人
            <input value={form.sales_rep} onChange={(e) => setForm({ ...form, sales_rep: e.target.value })} />
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
              <th>區域</th>
              <th>業務負責人</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((c) => (
              <tr key={c.id} className={c.is_active ? "" : "inactive-row"}>
                <td>{c.code}</td>
                <td>{c.name}</td>
                <td>{c.region ?? ""}</td>
                <td>{c.sales_rep ?? ""}</td>
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
