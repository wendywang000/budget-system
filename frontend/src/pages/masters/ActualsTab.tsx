import { ChangeEvent, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { ImportResult } from "../../types";
import { downloadBlob, filenameFromDisposition } from "../../utils/format";

export default function ActualsTab() {
  const [fiscalYear, setFiscalYear] = useState(new Date().getFullYear());
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleExport() {
    setError(null);
    try {
      const res = await api.get("/excel/actuals/export", {
        params: { fiscal_year: fiscalYear },
        responseType: "blob",
      });
      downloadBlob(res.data, filenameFromDisposition(res.headers["content-disposition"], `actuals_${fiscalYear}.xlsx`));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleImport(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post<ImportResult>("/excel/actuals/import", formData, {
        params: { fiscal_year: fiscalYear },
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  return (
    <div className="masters-tab">
      <div className="masters-form">
        <h3>實際數匯入 / 匯出</h3>
        <p className="hint-text">
          匯入格式：部門代號、部門名稱、科目代號、科目名稱、月份、金額。以「部門代號 + 科目代號 + 月份」為鍵，
          重複匯入會覆蓋既有金額，用於財務/ERP 系統匯出後的月結資料比對。
        </p>
        <div className="form-grid">
          <label>
            年度
            <input type="number" value={fiscalYear} onChange={(e) => setFiscalYear(Number(e.target.value))} />
          </label>
        </div>
        <div className="form-actions">
          <button onClick={handleExport} disabled={busy}>
            匯出年度實際數
          </button>
          <label className="file-button">
            {busy ? "處理中…" : "匯入 Excel"}
            <input type="file" accept=".xlsx" hidden onChange={handleImport} disabled={busy} />
          </label>
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {result && (
        <div className="banner banner-info">
          匯入完成:新增 {result.inserted}、更新 {result.updated}、略過 {result.skipped}。
          {result.errors.length > 0 && (
            <ul>
              {result.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
