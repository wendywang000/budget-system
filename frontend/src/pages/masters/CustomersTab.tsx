import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Customer } from "../../types";

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

  return (
    <div className="masters-tab">
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
