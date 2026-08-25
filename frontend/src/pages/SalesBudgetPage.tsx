import { Fragment, useEffect, useMemo, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import type { Customer, Product, SalesBudgetGridResponse, Salesperson } from "../types";
import { MONTHS, formatNumber } from "../utils/format";

type EditedQty = Record<string, number>; // key: `${customerId}-${productId}-${month}`
type EditedAmt = Record<string, number>;
type NewRow = { customer_id: number | ""; product_id: number | "" };

export default function SalesBudgetPage() {
  const [versions, setVersions] = useState<{ id: number; fiscal_year: number; name: string; status: string; is_default: boolean }[]>([]);
  const [salespeople, setSalespeople] = useState<Salesperson[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [salespersonId, setSalespersonId] = useState<number | null>(null);
  const [grid, setGrid] = useState<SalesBudgetGridResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [editedQty, setEditedQty] = useState<EditedQty>({});
  const [editedAmt, setEditedAmt] = useState<EditedAmt>({});
  const [extraRows, setExtraRows] = useState<{ customer_id: number; product_id: number }[]>([]);
  const [newRow, setNewRow] = useState<NewRow>({ customer_id: "", product_id: "" });

  useEffect(() => {
    Promise.all([
      api.get("/versions"),
      api.get<Salesperson[]>("/sales-budget/my-salespeople"),
      api.get<Customer[]>("/customers"),
      api.get<Product[]>("/products"),
    ])
      .then(([vRes, spRes, cRes, pRes]) => {
        setVersions(vRes.data);
        setSalespeople(spRes.data);
        setCustomers(cRes.data);
        setProducts(pRes.data);
      })
      .catch((err) => setError(apiErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      setVersionId((versions.find((v) => v.is_default) ?? versions[0]).id);
    }
  }, [versions, versionId]);

  useEffect(() => {
    if (salespersonId === null && salespeople.length > 0) {
      setSalespersonId(salespeople[0].id);
    }
  }, [salespeople, salespersonId]);

  async function loadGrid() {
    if (versionId === null || salespersonId === null) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<SalesBudgetGridResponse>("/sales-budget/grid", {
        params: { version_id: versionId, salesperson_id: salespersonId },
      });
      setGrid(res.data);
      setEditedQty({});
      setEditedAmt({});
      setExtraRows([]);
    } catch (err) {
      setError(apiErrorMessage(err));
      setGrid(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadGrid();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, salespersonId]);

  const rowKeys = useMemo(() => {
    const keys = new Set<string>();
    (grid?.rows ?? []).forEach((r) => keys.add(`${r.customer_id}-${r.product_id}`));
    extraRows.forEach((r) => keys.add(`${r.customer_id}-${r.product_id}`));
    return Array.from(keys);
  }, [grid, extraRows]);

  function rowMeta(key: string) {
    const [customerId, productId] = key.split("-").map(Number);
    const existing = grid?.rows.find((r) => r.customer_id === customerId && r.product_id === productId);
    const customer = customers.find((c) => c.id === customerId);
    const product = products.find((p) => p.id === productId);
    return { customerId, productId, existing, customer, product };
  }

  function qtyValue(customerId: number, productId: number, month: number): number {
    const key = `${customerId}-${productId}-${month}`;
    if (key in editedQty) return editedQty[key];
    const row = grid?.rows.find((r) => r.customer_id === customerId && r.product_id === productId);
    return row?.months[month]?.quantity ?? 0;
  }

  function amtValue(customerId: number, productId: number, month: number): number {
    const key = `${customerId}-${productId}-${month}`;
    if (key in editedAmt) return editedAmt[key];
    const row = grid?.rows.find((r) => r.customer_id === customerId && r.product_id === productId);
    return row?.months[month]?.amount ?? 0;
  }

  function rowTotal(customerId: number, productId: number): number {
    return MONTHS.reduce((sum, m) => sum + amtValue(customerId, productId, m), 0);
  }

  function addRow() {
    if (newRow.customer_id === "" || newRow.product_id === "") return;
    const cid = Number(newRow.customer_id);
    const pid = Number(newRow.product_id);
    if (!extraRows.some((r) => r.customer_id === cid && r.product_id === pid)) {
      setExtraRows((prev) => [...prev, { customer_id: cid, product_id: pid }]);
    }
    setNewRow({ customer_id: "", product_id: "" });
  }

  async function handleSave() {
    if (versionId === null || salespersonId === null) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const touched = new Set<string>([...Object.keys(editedQty), ...Object.keys(editedAmt)]);
      const cells = Array.from(touched).map((key) => {
        const [customerId, productId, month] = key.split("-").map(Number);
        return {
          customer_id: customerId,
          product_id: productId,
          month,
          currency: "TWD",
          quantity: qtyValue(customerId, productId, month),
          amount: amtValue(customerId, productId, month),
        };
      });
      const res = await api.put("/sales-budget/grid", {
        version_id: versionId,
        salesperson_id: salespersonId,
        cells,
        notes: {},
      });
      setMessage(`已儲存,更新 ${res.data.cells_updated} 格。`);
      await loadGrid();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSync() {
    if (versionId === null || !grid?.department) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.post("/sales-budget/sync", null, {
        params: { version_id: versionId, department_id: grid.department.id },
      });
      setMessage(`已同步至收入科目:更新 ${res.data.accounts_updated} 個科目,合計 ${formatNumber(res.data.grand_total)}。`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const grandTotal = rowKeys.reduce((sum, key) => {
    const [cid, pid] = key.split("-").map(Number);
    return sum + rowTotal(cid, pid);
  }, 0);

  return (
    <div className="page">
      <div className="page-toolbar">
        <label>
          預算版本
          <select value={versionId ?? ""} onChange={(e) => setVersionId(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.fiscal_year} - {v.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          銷售人員
          <select value={salespersonId ?? ""} onChange={(e) => setSalespersonId(Number(e.target.value))}>
            {salespeople.map((sp) => (
              <option key={sp.id} value={sp.id}>
                {sp.code} {sp.name}（{sp.department_name}）
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}
      {loading && <div className="page-loading">載入中…</div>}

      {grid && !loading && (
        <>
          <div className="page-toolbar">
            <label>
              新增客戶×產品組合
              <select
                value={newRow.customer_id}
                onChange={(e) => setNewRow({ ...newRow, customer_id: e.target.value ? Number(e.target.value) : "" })}
              >
                <option value="">選擇客戶</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.code} {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              &nbsp;
              <select
                value={newRow.product_id}
                onChange={(e) => setNewRow({ ...newRow, product_id: e.target.value ? Number(e.target.value) : "" })}
              >
                <option value="">選擇產品</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={addRow} disabled={!grid.editable}>
              加入列
            </button>
          </div>

          <div className="table-scroll">
            <table className="budget-grid sales-budget-grid">
              <thead>
                <tr>
                  <th className="col-account">客戶</th>
                  <th className="col-account">產品</th>
                  {MONTHS.map((m) => (
                    <th key={m} colSpan={2}>
                      {m} 月
                    </th>
                  ))}
                  <th>合計</th>
                </tr>
                <tr>
                  <th className="col-account" />
                  <th className="col-account" />
                  {MONTHS.map((m) => (
                    <Fragment key={m}>
                      <th className="sub-head">數量</th>
                      <th className="sub-head">金額</th>
                    </Fragment>
                  ))}
                  <th />
                </tr>
              </thead>
              <tbody>
                {rowKeys.map((key) => {
                  const { customerId, productId, customer, product } = rowMeta(key);
                  return (
                    <tr key={key}>
                      <td className="col-account">
                        {customer ? `${customer.code} ${customer.name}` : customerId}
                      </td>
                      <td className="col-account">{product ? `${product.code} ${product.name}` : productId}</td>
                      {MONTHS.map((m) => (
                        <Fragment key={m}>
                          <td className="col-number">
                            <input
                              type="number"
                              className="cell-input narrow"
                              disabled={!grid.editable}
                              value={qtyValue(customerId, productId, m)}
                              onChange={(e) =>
                                setEditedQty((prev) => ({
                                  ...prev,
                                  [`${customerId}-${productId}-${m}`]: Number(e.target.value) || 0,
                                }))
                              }
                            />
                          </td>
                          <td className="col-number">
                            <input
                              type="number"
                              className="cell-input narrow"
                              disabled={!grid.editable}
                              value={amtValue(customerId, productId, m)}
                              onChange={(e) =>
                                setEditedAmt((prev) => ({
                                  ...prev,
                                  [`${customerId}-${productId}-${m}`]: Number(e.target.value) || 0,
                                }))
                              }
                            />
                          </td>
                        </Fragment>
                      ))}
                      <td className="col-number row-total">{formatNumber(rowTotal(customerId, productId))}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={2}>合計</td>
                  {MONTHS.map((m) => (
                    <td key={m} colSpan={2} className="col-number">
                      {formatNumber(
                        rowKeys.reduce((sum, key) => {
                          const [cid, pid] = key.split("-").map(Number);
                          return sum + amtValue(cid, pid, m);
                        }, 0)
                      )}
                    </td>
                  ))}
                  <td className="col-number">{formatNumber(grandTotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="page-actions">
            <button onClick={handleSave} disabled={!grid.editable || saving}>
              {saving ? "處理中…" : "儲存變更"}
            </button>
            <button onClick={handleSync} disabled={!grid.editable || saving}>
              同步至收入科目
            </button>
          </div>
        </>
      )}
    </div>
  );
}
