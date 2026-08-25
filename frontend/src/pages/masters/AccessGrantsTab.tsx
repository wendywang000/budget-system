import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type {
  AccessGrant,
  Department,
  ExpenseFormat,
  GrantModule,
  Salesperson,
  User,
} from "../../types";
import { MODULE_LABELS } from "../../types";

const MODULES: GrantModule[] = ["budget", "sales", "expense", "capex", "report"];

const emptyForm = {
  user_id: "" as number | "",
  module: "budget" as GrantModule,
  department_id: "" as number | "",
  salesperson_id: "" as number | "",
  expense_format_id: "" as number | "",
};

export default function AccessGrantsTab() {
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [salespeople, setSalespeople] = useState<Salesperson[]>([]);
  const [formats, setFormats] = useState<ExpenseFormat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const [gRes, uRes, dRes, spRes, fRes] = await Promise.all([
        api.get<AccessGrant[]>("/access-grants"),
        api.get<User[]>("/auth/users"),
        api.get<Department[]>("/departments", { params: { active_only: true } }),
        api.get<Salesperson[]>("/salespeople", { params: { active_only: true } }),
        api.get<ExpenseFormat[]>("/expense-formats", { params: { active_only: true } }),
      ]);
      setGrants(gRes.data);
      setUsers(uRes.data.filter((u) => u.role === "dept_user"));
      setDepartments(dRes.data);
      setSalespeople(spRes.data);
      setFormats(fRes.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (form.user_id === "" || form.department_id === "") {
      setError("請選擇使用者與部門");
      return;
    }
    try {
      await api.post("/access-grants", {
        user_id: Number(form.user_id),
        module: form.module,
        department_id: Number(form.department_id),
        salesperson_id: form.salesperson_id === "" ? null : Number(form.salesperson_id),
        expense_format_id: form.expense_format_id === "" ? null : Number(form.expense_format_id),
      });
      setMessage("已新增授權");
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(grant: AccessGrant) {
    if (!window.confirm(`確定要刪除「${grant.user_name}」對「${grant.department_name}」的${MODULE_LABELS[grant.module]}授權嗎？`))
      return;
    setError(null);
    try {
      await api.delete(`/access-grants/${grant.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="masters-tab">
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>新增權限授予</h3>
        <p className="hint-text">
          部門使用者預設只能填報自己所屬部門的科目預算表(budget 模組)。若要讓某人額外處理其他部門,
          或處理銷售量預算/費用預算/資本支出/報表查詢,請在此新增授權;可再細至指定銷售人員或費用格式。
        </p>
        <div className="form-grid">
          <label>
            使用者
            <select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value ? Number(e.target.value) : "" })}>
              <option value="">請選擇</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}（{u.username}）
                </option>
              ))}
            </select>
          </label>
          <label>
            模組
            <select value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value as GrantModule })}>
              {MODULES.map((m) => (
                <option key={m} value={m}>
                  {MODULE_LABELS[m]}
                </option>
              ))}
            </select>
          </label>
          <label>
            部門
            <select
              value={form.department_id}
              onChange={(e) => setForm({ ...form, department_id: e.target.value ? Number(e.target.value) : "" })}
            >
              <option value="">請選擇</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {"　".repeat(d.level)}
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          {form.module === "sales" && (
            <label>
              限定銷售人員(留白＝該部門全部)
              <select
                value={form.salesperson_id}
                onChange={(e) => setForm({ ...form, salesperson_id: e.target.value ? Number(e.target.value) : "" })}
              >
                <option value="">（不限定）</option>
                {salespeople.map((sp) => (
                  <option key={sp.id} value={sp.id}>
                    {sp.code} {sp.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.module === "expense" && (
            <label>
              限定費用格式(留白＝該部門全部格式)
              <select
                value={form.expense_format_id}
                onChange={(e) => setForm({ ...form, expense_format_id: e.target.value ? Number(e.target.value) : "" })}
              >
                <option value="">（不限定）</option>
                {formats.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.code} {f.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="form-actions">
          <button type="submit">新增</button>
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
              <th>使用者</th>
              <th>模組</th>
              <th>部門</th>
              <th>限定範圍</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {grants.map((g) => (
              <tr key={g.id}>
                <td>{g.user_name}</td>
                <td>{MODULE_LABELS[g.module]}</td>
                <td>{g.department_name}</td>
                <td>{g.salesperson_name ?? g.expense_format_name ?? "（整部門）"}</td>
                <td className="action-cell">
                  <button onClick={() => handleDelete(g)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
