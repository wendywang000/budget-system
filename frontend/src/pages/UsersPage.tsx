import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { User, UserRole } from "../types";

const emptyForm = {
  username: "",
  full_name: "",
  password: "",
  role: "dept_user" as UserRole,
  department_id: "" as number | "",
};

export default function UsersPage() {
  const { departments } = useVersionsAndDepartments(false);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<User[]>("/auth/users");
      setUsers(res.data);
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
    try {
      await api.post("/auth/users", {
        username: form.username,
        full_name: form.full_name,
        password: form.password,
        role: form.role,
        department_id: form.department_id === "" ? null : Number(form.department_id),
      });
      setMessage("已新增使用者");
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function toggleActive(user: User) {
    setError(null);
    try {
      await api.patch(`/auth/users/${user.id}`, { is_active: !user.is_active });
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function resetPassword(user: User) {
    const password = window.prompt(`為「${user.full_name}」設定新密碼：`);
    if (!password) return;
    setError(null);
    try {
      await api.patch(`/auth/users/${user.id}`, { password });
      setMessage(`已重設 ${user.full_name} 的密碼`);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="page">
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>新增使用者</h3>
        <div className="form-grid">
          <label>
            帳號
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          </label>
          <label>
            姓名
            <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
          </label>
          <label>
            密碼
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          <label>
            角色
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}>
              <option value="dept_user">部門使用者</option>
              <option value="finance_admin">財務管理者</option>
            </select>
          </label>
          {form.role === "dept_user" && (
            <label>
              所屬部門
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
              <th>帳號</th>
              <th>姓名</th>
              <th>角色</th>
              <th>所屬部門</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.is_active ? "" : "inactive-row"}>
                <td>{u.username}</td>
                <td>{u.full_name}</td>
                <td>{u.role === "finance_admin" ? "財務管理者" : "部門使用者"}</td>
                <td>{u.department_name ?? ""}</td>
                <td>{u.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => resetPassword(u)}>重設密碼</button>
                  <button onClick={() => toggleActive(u)}>{u.is_active ? "停用" : "啟用"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
