import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Account, AccountCategoryOption, ImportResult } from "../../types";
import { CATEGORY_LABELS } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  category: "expense" as string,
  parent_id: "" as number | "",
  is_postable: true,
  sort_order: 0,
  is_active: true,
  note: "",
};

export default function AccountsTab() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<AccountCategoryOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [newCategory, setNewCategory] = useState({ code: "", name: "" });
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<Account[]>("/accounts", { params: { active_only: true } });
      setAccounts(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function loadCategories() {
    try {
      const res = await api.get<AccountCategoryOption[]>("/account-categories", { params: { active_only: false } });
      const categories = res.data.length ? res.data : [
        { id: 0, code: "revenue", name: "營業收入", sort_order: 10, is_active: true },
        { id: 0, code: "cost", name: "營業成本", sort_order: 20, is_active: true },
        { id: 0, code: "expense", name: "營業費用", sort_order: 30, is_active: true },
        { id: 0, code: "capex", name: "資本支出", sort_order: 40, is_active: true },
      ];
      setCategoryOptions(categories);
      if (!form.id && !categories.some((o) => o.code === form.category)) {
        const first = categories[0]?.code ?? "expense";
        setForm((prev) => ({ ...prev, category: first }));
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    loadCategories();
  }, []);

  function startEdit(account: Account) {
    setForm({
      id: account.id,
      code: account.code,
      name: account.name,
      category: account.category,
      parent_id: account.parent_id ?? "",
      is_postable: account.is_postable,
      sort_order: account.sort_order,
      is_active: account.is_active,
      note: account.note ?? "",
    });
  }

  async function handleAddCategory() {
    const code = newCategory.code.trim();
    const name = newCategory.name.trim();
    if (!code || !name) {
      setError("請輸入類別代碼與名稱");
      return;
    }
    try {
      setBusy(true);
      const saved = await api.post<AccountCategoryOption>("/account-categories", { code, name, sort_order: 0, is_active: true });
      setCategoryOptions((prev) => [...prev, saved.data].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)));
      setForm((prev) => ({ ...prev, category: saved.data.code }));
      setNewCategory({ code: "", name: "" });
      setMessage(`已新增類別「${saved.data.name}」`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const payload = {
      code: form.code,
      name: form.name,
      category: form.category,
      parent_id: form.parent_id === "" ? null : Number(form.parent_id),
      is_postable: form.is_postable,
      sort_order: form.sort_order,
      is_active: form.is_active,
      note: form.note || null,
    };
    try {
      if (form.id === null) {
        await api.post("/accounts", payload);
        setMessage("已新增科目");
      } else {
        await api.patch(`/accounts/${form.id}`, payload);
        setMessage("已更新科目");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(account: Account) {
    if (!window.confirm(`確定要刪除科目「${account.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/accounts/${account.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    setError(null);
    try {
      const res = await api.get("/excel/accounts/template", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "accounts_template.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/accounts/export", { responseType: "blob" });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "accounts.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleImport(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const shouldReplace = window.confirm("這會直接刪除所有未出現在新檔中的舊科目，是否用新檔完整覆蓋？");
    setBusy(true);
    setError(null);
    setMessage(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post<ImportResult>(`/excel/accounts/import?replace=${shouldReplace}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const r = res.data;
      setMessage(
        `匯入完成:新增 ${r.inserted}、更新 ${r.updated}${r.deactivated ? `、停用 ${r.deactivated}` : ""}、略過 ${r.skipped}。`,
      );
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
        <span className="hint-text">可匯入自家會計科目表，支援上層科目代碼/名稱與類別對照</span>
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
        <h3>{form.id === null ? "新增科目" : `編輯科目 #${form.id}`}</h3>
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
            類別
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              {categoryOptions.map((c) => (
                <option key={c.id} value={c.code}>
                  {CATEGORY_LABELS[c.code as keyof typeof CATEGORY_LABELS] ?? c.name}
                </option>
              ))}
            </select>
          </label>
          <div className="wide-field" style={{ display: "flex", gap: 8, alignItems: "end" }}>
            <label style={{ flex: 1 }}>
              新增類別代碼
              <input
                value={newCategory.code}
                onChange={(e) => setNewCategory((prev) => ({ ...prev, code: e.target.value }))}
                placeholder="例如: admin"
              />
            </label>
            <label style={{ flex: 1 }}>
              新增類別名稱
              <input
                value={newCategory.name}
                onChange={(e) => setNewCategory((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="例如: 行政費用"
              />
            </label>
            <button type="button" onClick={handleAddCategory} disabled={busy}>
              新增類別
            </button>
          </div>
          <label>
            上層科目
            <select
              value={form.parent_id}
              onChange={(e) => setForm({ ...form, parent_id: e.target.value ? Number(e.target.value) : "" })}
            >
              <option value="">（無，最上層）</option>
              {accounts
                .filter((a) => a.id !== form.id)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {"　".repeat(a.level)}
                    {a.code} {a.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_postable}
              onChange={(e) => setForm({ ...form, is_postable: e.target.checked })}
            />
            可直接填報金額（葉科目）
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
          <label className="wide-field">
            備註
            <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
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
              <th>類別</th>
              <th>葉科目</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => {
              const categoryLabel =
                CATEGORY_LABELS[a.category as keyof typeof CATEGORY_LABELS] ??
                categoryOptions.find((c) => c.code === a.category)?.name ??
                a.category;
              return (
                <tr key={a.id} className={a.is_active ? "" : "inactive-row"}>
                  <td>{a.code}</td>
                  <td style={{ paddingLeft: `${a.level * 16}px` }}>{a.name}</td>
                  <td>{categoryLabel}</td>
                  <td>{a.is_postable && !a.has_children ? "是" : "否"}</td>
                  <td>{a.is_active ? "啟用" : "停用"}</td>
                  <td className="action-cell">
                    <button onClick={() => startEdit(a)}>編輯</button>
                    <button onClick={() => handleDelete(a)}>刪除</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
