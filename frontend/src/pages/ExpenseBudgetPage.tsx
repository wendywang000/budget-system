import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { ExpenseFormat, ExpenseGridResponse } from "../types";
import { MONTHS, formatNumber } from "../utils/format";

type Edited = Record<string, number>; // key: `${column_key}-${month}`

export default function ExpenseBudgetPage() {
  const { versions, departments, loading: refLoading } = useVersionsAndDepartments(true);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [formats, setFormats] = useState<ExpenseFormat[]>([]);
  const [formatId, setFormatId] = useState<number | null>(null);
  const [grid, setGrid] = useState<ExpenseGridResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [edited, setEdited] = useState<Edited>({});

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      setVersionId((versions.find((v) => v.is_default) ?? versions[0]).id);
    }
  }, [versions, versionId]);

  useEffect(() => {
    if (departmentId === null && departments.length > 0) {
      setDepartmentId(departments[0].id);
    }
  }, [departments, departmentId]);

  useEffect(() => {
    if (departmentId === null) return;
    setFormatId(null);
    api
      .get<ExpenseFormat[]>("/expense/formats-for-department", { params: { department_id: departmentId } })
      .then((res) => {
        setFormats(res.data);
        if (res.data.length > 0) setFormatId(res.data[0].id);
      })
      .catch((err) => setError(apiErrorMessage(err)));
  }, [departmentId]);

  async function loadGrid() {
    if (versionId === null || departmentId === null || formatId === null) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<ExpenseGridResponse>("/expense/grid", {
        params: { version_id: versionId, department_id: departmentId, format_id: formatId },
      });
      setGrid(res.data);
      setEdited({});
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
  }, [versionId, departmentId, formatId]);

  function cellValue(columnKey: string, month: number): number {
    const key = `${columnKey}-${month}`;
    if (key in edited) return edited[key];
    const row = grid?.rows.find((r) => r.column_key === columnKey);
    return row?.months[month] ?? 0;
  }

  function rowTotal(columnKey: string): number {
    return MONTHS.reduce((sum, m) => sum + cellValue(columnKey, m), 0);
  }

  const monthTotals: Record<number, number> = {};
  for (const m of MONTHS) {
    monthTotals[m] = (grid?.rows ?? []).reduce((sum, r) => sum + cellValue(r.column_key, m), 0);
  }
  const grandTotal = MONTHS.reduce((sum, m) => sum + monthTotals[m], 0);

  async function handleSave() {
    if (versionId === null || departmentId === null || formatId === null) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const cells = Object.entries(edited).map(([key, amount]) => {
        const idx = key.lastIndexOf("-");
        const column_key = key.slice(0, idx);
        const month = Number(key.slice(idx + 1));
        return { column_key, month, amount };
      });
      const res = await api.put("/expense/grid", {
        version_id: versionId,
        department_id: departmentId,
        format_id: formatId,
        cells,
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
    if (versionId === null || departmentId === null || formatId === null) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api.post("/expense/sync", null, {
        params: { version_id: versionId, department_id: departmentId, format_id: formatId },
      });
      setMessage(`已同步至會計科目,合計 ${formatNumber(res.data.grand_total)}。`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (refLoading) return <div className="page-loading">載入中…</div>;

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
          部門
          <select value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {"　".repeat(d.level)}
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          費用格式
          <select value={formatId ?? ""} onChange={(e) => setFormatId(Number(e.target.value))}>
            {formats.map((f) => (
              <option key={f.id} value={f.id}>
                {f.code} {f.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}
      {formats.length === 0 && !error && <div className="empty-state">此部門目前沒有可填報的費用格式。</div>}
      {loading && <div className="page-loading">載入中…</div>}

      {grid && !loading && (
        <>
          <div className="grid-meta">
            {grid.resolved_account ? (
              <span>對應科目:{grid.resolved_account.account_code} {grid.resolved_account.account_name}</span>
            ) : (
              <span className="readonly-note">此部門功能別尚未設定對應科目,無法同步</span>
            )}
            {!grid.editable && <span className="readonly-note">目前唯讀,無法編輯</span>}
          </div>

          <div className="table-scroll">
            <table className="budget-grid">
              <thead>
                <tr>
                  <th className="col-account">費用欄位</th>
                  {MONTHS.map((m) => (
                    <th key={m}>{m} 月</th>
                  ))}
                  <th>合計</th>
                </tr>
              </thead>
              <tbody>
                {grid.format.columns.map((col) => (
                  <tr key={col.key}>
                    <td className="col-account">{col.label}</td>
                    {MONTHS.map((m) => (
                      <td key={m} className="col-number">
                        <input
                          type="number"
                          className="cell-input"
                          disabled={!grid.editable}
                          value={cellValue(col.key, m)}
                          onChange={(e) =>
                            setEdited((prev) => ({ ...prev, [`${col.key}-${m}`]: Number(e.target.value) || 0 }))
                          }
                        />
                      </td>
                    ))}
                    <td className="col-number row-total">{formatNumber(rowTotal(col.key))}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="col-account">合計</td>
                  {MONTHS.map((m) => (
                    <td key={m} className="col-number">
                      {formatNumber(monthTotals[m])}
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
            <button onClick={handleSync} disabled={!grid.editable || saving || !grid.resolved_account}>
              同步至會計科目
            </button>
          </div>
        </>
      )}
    </div>
  );
}
