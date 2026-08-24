import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { GridResponse, GridRow } from "../types";
import { SUBMISSION_STATUS_LABELS } from "../types";
import { MONTHS, downloadBlob, filenameFromDisposition, formatNumber } from "../utils/format";

type EditedCells = Record<string, number>; // key: `${accountId}-${month}`
type EditedNotes = Record<number, string | null>;

export default function BudgetGridPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "finance_admin";
  const { versions, departments, loading: refLoading } = useVersionsAndDepartments(true);

  const [versionId, setVersionId] = useState<number | null>(null);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [grid, setGrid] = useState<GridResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [edited, setEdited] = useState<EditedCells>({});
  const [editedNotes, setEditedNotes] = useState<EditedNotes>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      const preferred = versions.find((v) => v.is_default) ?? versions[0];
      setVersionId(preferred.id);
    }
  }, [versions, versionId]);

  useEffect(() => {
    if (departmentId === null && departments.length > 0) {
      setDepartmentId(departments[0].id);
    }
  }, [departments, departmentId]);

  const loadGrid = async () => {
    if (versionId === null || departmentId === null) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<GridResponse>("/budget/grid", {
        params: { version_id: versionId, department_id: departmentId },
      });
      setGrid(res.data);
      setEdited({});
      setEditedNotes({});
    } catch (err) {
      setError(apiErrorMessage(err));
      setGrid(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGrid();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, departmentId]);

  const dirty = Object.keys(edited).length > 0 || Object.keys(editedNotes).length > 0;

  function cellValue(row: GridRow, month: number): number {
    const key = `${row.account_id}-${month}`;
    return key in edited ? edited[key] : row.months[month] ?? 0;
  }

  function noteValue(row: GridRow): string {
    if (row.account_id in editedNotes) return editedNotes[row.account_id] ?? "";
    return row.note ?? "";
  }

  function handleCellChange(row: GridRow, month: number, raw: string) {
    const key = `${row.account_id}-${month}`;
    const parsed = raw.trim() === "" ? 0 : Number(raw);
    if (Number.isNaN(parsed)) return;
    setEdited((prev) => ({ ...prev, [key]: parsed }));
  }

  function handleNoteChange(row: GridRow, value: string) {
    setEditedNotes((prev) => ({ ...prev, [row.account_id]: value }));
  }

  function rowTotal(row: GridRow): number {
    return MONTHS.reduce((sum, m) => sum + cellValue(row, m), 0);
  }

  const monthTotals = useMemo(() => {
    if (!grid) return {} as Record<number, number>;
    const totals: Record<number, number> = {};
    for (const m of MONTHS) totals[m] = 0;
    for (const row of grid.rows) {
      if (!row.is_postable) continue;
      for (const m of MONTHS) totals[m] += cellValue(row, m);
    }
    return totals;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grid, edited]);

  const grandTotal = MONTHS.reduce((sum, m) => sum + (monthTotals[m] ?? 0), 0);

  async function handleSave() {
    if (!grid || versionId === null || departmentId === null) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const cells = Object.entries(edited).map(([key, amount]) => {
        const [accountId, month] = key.split("-").map(Number);
        return { account_id: accountId, month, amount };
      });
      const notes: Record<number, string | null> = {};
      for (const [accountId, value] of Object.entries(editedNotes)) {
        notes[Number(accountId)] = value === "" ? null : value;
      }
      const res = await api.put("/budget/grid", {
        version_id: versionId,
        department_id: departmentId,
        cells,
        notes,
      });
      setMessage(`已儲存,更新 ${res.data.updated} 格、刪除 ${res.data.deleted} 格。`);
      await loadGrid();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    if (versionId === null || departmentId === null) return;
    if (dirty && !window.confirm("有未儲存的變更,確定要先儲存再送出嗎?")) return;
    setSaving(true);
    setError(null);
    try {
      if (dirty) await handleSave();
      await api.post("/budget/submit", { version_id: versionId, department_id: departmentId });
      setMessage("已送出,等待財務審核。");
      await loadGrid();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleExport() {
    if (versionId === null || departmentId === null) return;
    try {
      const res = await api.get("/excel/budget/export", {
        params: { version_id: versionId, department_id: departmentId },
        responseType: "blob",
      });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], "budget.xlsx"));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleTemplate() {
    try {
      const res = await api.get("/excel/budget/template", { responseType: "blob" });
      downloadBlob(res.data, "budget_template.xlsx");
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleImport(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || versionId === null || departmentId === null) return;
    const formData = new FormData();
    formData.append("file", file);
    setSaving(true);
    setError(null);
    try {
      const res = await api.post("/excel/budget/import", formData, {
        params: { version_id: versionId, department_id: departmentId },
        headers: { "Content-Type": "multipart/form-data" },
      });
      const r = res.data;
      setMessage(`匯入完成:新增 ${r.inserted}、更新 ${r.updated}、略過 ${r.skipped}。`);
      if (r.errors?.length) setError(r.errors.join("\n"));
      await loadGrid();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  if (refLoading) return <div className="page-loading">載入中…</div>;
  if (departments.length === 0) return <div className="empty-state">目前沒有可編列的部門。</div>;

  return (
    <div className="page">
      <div className="page-toolbar">
        <label>
          預算版本
          <select value={versionId ?? ""} onChange={(e) => setVersionId(Number(e.target.value))}>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.fiscal_year} - {v.name}（{v.status}）
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
        <div className="toolbar-spacer" />
        <button onClick={handleTemplate}>下載範本</button>
        <button onClick={() => fileInputRef.current?.click()} disabled={!grid?.editable}>
          匯入 Excel
        </button>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={handleImport} />
        <button onClick={handleExport}>匯出 Excel</button>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}

      {loading && <div className="page-loading">載入中…</div>}

      {grid && !loading && (
        <>
          <div className="grid-meta">
            <span className={`status-pill status-${grid.submission_status}`}>
              {SUBMISSION_STATUS_LABELS[grid.submission_status]}
            </span>
            {!grid.editable && <span className="readonly-note">目前唯讀,無法編輯</span>}
            {grid.submission_comment && <span className="submission-comment">審核意見:{grid.submission_comment}</span>}
          </div>

          <div className="table-scroll">
            <table className="budget-grid">
              <thead>
                <tr>
                  <th className="col-account">科目</th>
                  {MONTHS.map((m) => (
                    <th key={m}>{m} 月</th>
                  ))}
                  <th>合計</th>
                  <th className="col-note">備註</th>
                </tr>
              </thead>
              <tbody>
                {grid.rows.map((row) => (
                  <tr key={row.account_id} className={row.is_postable ? "" : "group-row"}>
                    <td className="col-account" style={{ paddingLeft: `${row.level * 16 + 8}px` }}>
                      <span className="account-code">{row.account_code}</span> {row.account_name}
                    </td>
                    {MONTHS.map((m) => (
                      <td key={m} className="col-number">
                        {row.is_postable ? (
                          <input
                            type="number"
                            className="cell-input"
                            value={cellValue(row, m)}
                            disabled={!grid.editable}
                            onChange={(e) => handleCellChange(row, m, e.target.value)}
                          />
                        ) : (
                          formatNumber(row.months[m] ?? 0)
                        )}
                      </td>
                    ))}
                    <td className="col-number row-total">{formatNumber(rowTotal(row))}</td>
                    <td className="col-note">
                      {row.is_postable ? (
                        <input
                          type="text"
                          className="note-input"
                          value={noteValue(row)}
                          disabled={!grid.editable}
                          onChange={(e) => handleNoteChange(row, e.target.value)}
                        />
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="col-account">月合計</td>
                  {MONTHS.map((m) => (
                    <td key={m} className="col-number">
                      {formatNumber(monthTotals[m] ?? 0)}
                    </td>
                  ))}
                  <td className="col-number">{formatNumber(grandTotal)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="page-actions">
            <button onClick={handleSave} disabled={!grid.editable || !dirty || saving}>
              {saving ? "處理中…" : "儲存變更"}
            </button>
            <button onClick={handleSubmit} disabled={!grid.editable || saving} className="primary">
              送出審核
            </button>
            {isAdmin && (
              <span className="admin-hint">財務管理者身分,可跨部門編輯與核定</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
