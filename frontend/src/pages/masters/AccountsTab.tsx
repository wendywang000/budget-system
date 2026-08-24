import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Account, AccountCategory } from "../../types";
import { CATEGORY_LABELS } from "../../types";

const CATEGORY_OPTIONS: AccountCategory[] = ["revenue", "cost", "expense", "capex"];

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  category: "expense" as AccountCategory,
  parent_id: "" as number | "",
  is_postable: true,
  sort_order: 0,
  is_active: true,
  note: "",
};

export default function AccountsTab() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<Account[]>("/accounts", { params: { active_only: false } });
      setAccounts(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
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

  return (
    <div className="masters-tab">
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
              onChange={(e) => setForm({ ...form, category: e.target.value as AccountCategory })}
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {CATEGORY_LABELS[c]}
                </option>
              ))}
            </select>
          </label>
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
            {accounts.map((a) => (
              <tr key={a.id} className={a.is_active ? "" : "inactive-row"}>
                <td>{a.code}</td>
                <td style={{ paddingLeft: `${a.level * 16}px` }}>{a.name}</td>
                <td>{CATEGORY_LABELS[a.category]}</td>
                <td>{a.is_postable && !a.has_children ? "是" : "否"}</td>
                <td>{a.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(a)}>編輯</button>
                  <button onClick={() => handleDelete(a)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
