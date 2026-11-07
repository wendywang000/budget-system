import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Department, ImportResult, Salesperson } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  department_id: "" as number | "",
  is_active: true,
};

export default function SalespeopleTab() {
  const [salespeople, setSalespeople] = useState<Salesperson[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const [spRes, dRes] = await Promise.all([
        api.get<Salesperson[]>("/salespeople", { params: { active_only: false } }),
        api.get<Department[]>("/departments", { params: { active_only: true } }),
      ]);
      setSalespeople(spRes.data);
      setDepartments(dRes.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(sp: Salesperson) {
    setForm({ id: sp.id, code: sp.code, name: sp.name, department_id: sp.department_id, is_active: sp.is_active });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (form.department_id === "") {
      setError("請選擇預算單位(部門)");
      return;
    }
    const payload = {
      code: form.code,
      name: form.name,
      department_id: Number(form.department_id),
      is_active: form.is_active,
    };
    try {
      if (form.id === null) {
        await api.post("/salespeople", payload);
        setMessage("已新增銷售人員");
      } else {
        await api.patch(`/salespeople/${form.id}`, payload);
        setMessage("已更新銷售人員");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(sp: Salesperson) {
    if (!window.confirm(`確定要刪除銷售人員「${sp.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/salespeople/${sp.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    setError(null);
    try {
      const res = await api.get("/excel/salespeople/template", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "salespeople_template.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/salespeople/export", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "salespeople.xlsx"));
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
      const res = await api.post<ImportResult>("/excel/salespeople/import", formData, {
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
        <span className="hint-text">可匯入銷售人員資料，支援部門、代碼與姓名維護</span>
        <div className="toolbar-spacer" />
        <button type="button" onClick={handleTemplate} disabled={busy}>下載範本</button>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={busy}>{busy ? "處理中…" : "匯入 Excel"}</button>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={handleImport} />
        <button type="button" onClick={handleExport} disabled={busy}>匯出 Excel</button>
      </div>
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增銷售人員" : `編輯銷售人員 #${form.id}`}</h3>
        <p className="hint-text">銷售量預算以銷售人員填報,再依所屬預算單位滾算至部門彙總。</p>
        <div className="form-grid">
          <label>
            代號
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
          </label>
          <label>
            姓名
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            所屬預算單位
            <select
              value={form.department_id}
              onChange={(e) => setForm({ ...form, department_id: e.target.value ? Number(e.target.value) : "" })}
              required
            >
              <option value="">請選擇部門</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {"　".repeat(d.level)}
                  {d.name}
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
              <th>姓名</th>
              <th>所屬預算單位</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {salespeople.map((sp) => (
              <tr key={sp.id} className={sp.is_active ? "" : "inactive-row"}>
                <td>{sp.code}</td>
                <td>{sp.name}</td>
                <td>{sp.department_name}</td>
                <td>{sp.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(sp)}>編輯</button>
                  <button onClick={() => handleDelete(sp)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
