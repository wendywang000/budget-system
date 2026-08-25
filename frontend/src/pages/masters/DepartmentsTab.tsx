import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Department, DeptKind, ExpenseFunction, ImportResult } from "../../types";
import { DEPT_KIND_LABELS, FUNCTION_LABELS } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

const KIND_OPTIONS: DeptKind[] = ["company", "division", "department", "cost_center", "project"];
const FUNCTION_OPTIONS: ExpenseFunction[] = ["sales", "admin", "rd", "manufacturing"];

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  name_zh_hans: "",
  name_en: "",
  kind: "department" as DeptKind,
  parent_id: "" as number | "",
  manager: "",
  function: "" as ExpenseFunction | "",
  sort_order: 0,
  is_active: true,
};

export default function DepartmentsTab() {
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
      const res = await api.get<Department[]>("/departments", { params: { active_only: false } });
      setDepartments(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(dept: Department) {
    setForm({
      id: dept.id,
      code: dept.code,
      name: dept.name,
      name_zh_hans: dept.name_zh_hans ?? "",
      name_en: dept.name_en ?? "",
      kind: dept.kind,
      parent_id: dept.parent_id ?? "",
      manager: dept.manager ?? "",
      function: dept.function ?? "",
      sort_order: dept.sort_order,
      is_active: dept.is_active,
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const payload = {
      code: form.code,
      name: form.name,
      name_zh_hans: form.name_zh_hans || null,
      name_en: form.name_en || null,
      kind: form.kind,
      parent_id: form.parent_id === "" ? null : Number(form.parent_id),
      manager: form.manager || null,
      function: form.function || null,
      sort_order: form.sort_order,
      is_active: form.is_active,
    };
    try {
      if (form.id === null) {
        await api.post("/departments", payload);
        setMessage("已新增部門");
      } else {
        await api.patch(`/departments/${form.id}`, payload);
        setMessage("已更新部門");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(dept: Department) {
    if (!window.confirm(`確定要刪除部門「${dept.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/departments/${dept.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    setError(null);
    try {
      const res = await api.get("/excel/departments/template", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "departments_template.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/departments/export", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "departments.xlsx"));
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
      const res = await api.post<ImportResult>("/excel/departments/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const r = res.data;
      setMessage(`匯入完成:新增 ${r.inserted}、更新 ${r.updated}、略過 ${r.skipped}。`);
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
        <span className="hint-text">可用 Excel 批次匯入部門/成本中心,「上層部門代號」欄位用來建立組織樹</span>
        <div className="toolbar-spacer" />
        <button type="button" onClick={handleTemplate} disabled={busy}>
          下載範本
        </button>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={busy}>
          {busy ? "處理中…" : "匯入 Excel"}
        </button>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={handleImport} />
        <button type="button" onClick={handleExport} disabled={busy}>
          匯出 Excel
        </button>
      </div>

      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增部門" : `編輯部門 #${form.id}`}</h3>
        <div className="form-grid">
          <label>
            代號
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required />
          </label>
          <label>
            名稱(繁體中文)
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            名稱(簡體中文)
            <input value={form.name_zh_hans} onChange={(e) => setForm({ ...form, name_zh_hans: e.target.value })} />
          </label>
          <label>
            名稱(英文)
            <input value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} />
          </label>
          <label>
            類型
            <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as DeptKind })}>
              {KIND_OPTIONS.map((k) => (
                <option key={k} value={k}>
                  {DEPT_KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
          <label>
            上層部門
            <select
              value={form.parent_id}
              onChange={(e) => setForm({ ...form, parent_id: e.target.value ? Number(e.target.value) : "" })}
            >
              <option value="">（無，最上層）</option>
              {departments
                .filter((d) => d.id !== form.id)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {"　".repeat(d.level)}
                    {d.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            主管
            <input value={form.manager} onChange={(e) => setForm({ ...form, manager: e.target.value })} />
          </label>
          <label>
            作業功能別(費用預算科目對應用)
            <select
              value={form.function}
              onChange={(e) => setForm({ ...form, function: e.target.value as ExpenseFunction | "" })}
            >
              <option value="">（未設定）</option>
              {FUNCTION_OPTIONS.map((f) => (
                <option key={f} value={f}>
                  {FUNCTION_LABELS[f]}
                </option>
              ))}
            </select>
          </label>
          <label>
            排序
            <input
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })}
            />
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
              <th>類型</th>
              <th>主管</th>
              <th>功能別</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {departments.map((d) => (
              <tr key={d.id} className={d.is_active ? "" : "inactive-row"}>
                <td>{d.code}</td>
                <td style={{ paddingLeft: `${d.level * 16}px` }}>{d.name}</td>
                <td>{DEPT_KIND_LABELS[d.kind]}</td>
                <td>{d.manager ?? ""}</td>
                <td>{d.function ? FUNCTION_LABELS[d.function] : ""}</td>
                <td>{d.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(d)}>編輯</button>
                  <button onClick={() => handleDelete(d)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
