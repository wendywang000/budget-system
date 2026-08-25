import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { Account, ExpenseFormat, ExpenseFunction } from "../../types";
import { FUNCTION_LABELS } from "../../types";

const FUNCTIONS: ExpenseFunction[] = ["sales", "admin", "rd", "manufacturing"];

type ColumnDraft = { key: string; label: string };

const emptyForm = {
  id: null as number | null,
  code: "",
  name: "",
  sort_order: 0,
  columns: [{ key: "amount", label: "金額" }] as ColumnDraft[],
  accountByFunction: {} as Partial<Record<ExpenseFunction, number | "">>,
};

export default function ExpenseFormatsTab() {
  const [formats, setFormats] = useState<ExpenseFormat[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const [fRes, aRes] = await Promise.all([
        api.get<ExpenseFormat[]>("/expense-formats", { params: { active_only: false } }),
        api.get<Account[]>("/accounts", { params: { active_only: true } }),
      ]);
      setFormats(fRes.data);
      setAccounts(aRes.data.filter((a) => !a.has_children));
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEdit(fmt: ExpenseFormat) {
    const accountByFunction: Partial<Record<ExpenseFunction, number | "">> = {};
    for (const m of fmt.account_maps) accountByFunction[m.function] = m.account_id;
    setForm({
      id: fmt.id,
      code: fmt.code,
      name: fmt.name,
      sort_order: fmt.sort_order,
      columns: fmt.columns.map((c) => ({ key: c.key, label: c.label })),
      accountByFunction,
    });
  }

  function updateColumn(index: number, field: keyof ColumnDraft, value: string) {
    setForm((prev) => {
      const columns = [...prev.columns];
      columns[index] = { ...columns[index], [field]: value };
      return { ...prev, columns };
    });
  }

  function addColumn() {
    setForm((prev) => ({ ...prev, columns: [...prev.columns, { key: "", label: "" }] }));
  }

  function removeColumn(index: number) {
    setForm((prev) => ({ ...prev, columns: prev.columns.filter((_, i) => i !== index) }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (form.columns.some((c) => !c.key.trim() || !c.label.trim())) {
      setError("每個欄位都要有代號與名稱");
      return;
    }
    const accountMaps = FUNCTIONS.filter((fn) => form.accountByFunction[fn]).map((fn) => ({
      function: fn,
      account_id: Number(form.accountByFunction[fn]),
    }));
    const payload = {
      code: form.code,
      name: form.name,
      sort_order: form.sort_order,
      columns: form.columns.map((c, i) => ({ key: c.key.trim(), label: c.label.trim(), sort_order: i })),
      account_maps: accountMaps,
    };
    try {
      if (form.id === null) {
        await api.post("/expense-formats", payload);
        setMessage("已新增費用格式");
      } else {
        await api.patch(`/expense-formats/${form.id}`, payload);
        setMessage("已更新費用格式");
      }
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(fmt: ExpenseFormat) {
    if (!window.confirm(`確定要刪除費用格式「${fmt.name}」嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/expense-formats/${fmt.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="masters-tab">
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>{form.id === null ? "新增費用收集格式" : `編輯費用格式 #${form.id}`}</h3>
        <p className="hint-text">
          每種費用格式可以有自己的欄位組合(例如直接用人費會拆薪資/加班費/獎金/勞健保…多欄),
          各欄位金額加總後,依部門功能別(銷/管/研/製)對應到不同會計科目。
        </p>
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
            排序
            <input
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })}
            />
          </label>
        </div>

        <h4>欄位設定</h4>
        <div className="column-list">
          {form.columns.map((col, i) => (
            <div key={i} className="column-row">
              <input
                placeholder="欄位代號(如 salary)"
                value={col.key}
                onChange={(e) => updateColumn(i, "key", e.target.value)}
              />
              <input
                placeholder="欄位名稱(如 薪資)"
                value={col.label}
                onChange={(e) => updateColumn(i, "label", e.target.value)}
              />
              <button type="button" onClick={() => removeColumn(i)} disabled={form.columns.length <= 1}>
                移除
              </button>
            </div>
          ))}
          <button type="button" onClick={addColumn}>
            + 新增欄位
          </button>
        </div>

        <h4>作業功能別 → 會計科目對應</h4>
        <div className="form-grid">
          {FUNCTIONS.map((fn) => (
            <label key={fn}>
              {FUNCTION_LABELS[fn]}
              <select
                value={form.accountByFunction[fn] ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    accountByFunction: {
                      ...form.accountByFunction,
                      [fn]: e.target.value ? Number(e.target.value) : "",
                    },
                  })
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
          ))}
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
              <th>欄位</th>
              <th>科目對應</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {formats.map((f) => (
              <tr key={f.id} className={f.is_active ? "" : "inactive-row"}>
                <td>{f.code}</td>
                <td>{f.name}</td>
                <td>{f.columns.map((c) => c.label).join("、")}</td>
                <td>
                  {f.account_maps.map((m) => `${FUNCTION_LABELS[m.function]}:${m.account_code}`).join("　")}
                </td>
                <td>{f.is_active ? "啟用" : "停用"}</td>
                <td className="action-cell">
                  <button onClick={() => startEdit(f)}>編輯</button>
                  <button onClick={() => handleDelete(f)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
