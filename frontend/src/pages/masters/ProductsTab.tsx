import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Account, Product } from "../../types";

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  category: "",
  unit: "PCS",
  unit_price: 0,
  unit_cost: 0,
  revenue_account_id: "" as number | "",
  is_active: true,
};

export default function ProductsTab() {
  const [products, setProducts] = useState<Product[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const [pRes, aRes] = await Promise.all([
        api.get<Product[]>("/products", { params: { active_only: false } }),
        api.get<Account[]>("/accounts", { params: { active_only: true } }),
      ]);
      setProducts(pRes.data);
      setAccounts(aRes.data.filter((a) => a.category === "revenue" && !a.has_children));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(product: Product) {
    setForm({
      id: product.id,
      code: product.code,
      name: product.name,
      category: product.category ?? "",
      unit: product.unit,
      unit_price: product.unit_price,
      unit_cost: product.unit_cost,
      revenue_account_id: product.revenue_account_id ?? "",
      is_active: product.is_active,
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    const payload = {
      code: form.code,
      name: form.name,
      category: form.category || null,
      unit: form.unit,
      unit_price: form.unit_price,
      unit_cost: form.unit_cost,
      revenue_account_id: form.revenue_account_id === "" ? null : Number(form.revenue_account_id),
      is_active: form.is_active,
    };
    try {
      if (form.id === null) {
        await api.post("/products", payload);
        setMessage("已新增產品");
      } else {
        await api.patch(`/products/${form.id}`, payload);
        setMessage("已更新產品");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(product: Product) {
    if (!window.confirm(`確定要刪除產品「${product.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/products/${product.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="masters-tab">
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增產品" : `編輯產品 #${form.id}`}</h3>
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
            分類
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </label>
          <label>
            單位
            <input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
          </label>
          <label>
            標準售價
            <input
              type="number"
              value={form.unit_price}
              onChange={(e) => setForm({ ...form, unit_price: Number(e.target.value) })}
            />
          </label>
          <label>
            標準成本
            <input
              type="number"
              value={form.unit_cost}
              onChange={(e) => setForm({ ...form, unit_cost: Number(e.target.value) })}
            />
          </label>
          <label>
            對應收入科目(供同步預算表用)
            <select
              value={form.revenue_account_id}
              onChange={(e) =>
                setForm({ ...form, revenue_account_id: e.target.value ? Number(e.target.value) : "" })
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
              <th>分類</th>
              <th>單位</th>
              <th>標準售價</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className={p.is_active ? "" : "inactive-row"}>
                <td>{p.code}</td>
                <td>{p.name}</td>
                <td>{p.category ?? ""}</td>
                <td>{p.unit}</td>
                <td className="col-number">{p.unit_price.toLocaleString()}</td>
                <td>{p.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(p)}>編輯</button>
                  <button onClick={() => handleDelete(p)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
