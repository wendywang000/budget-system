import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { SummaryResponse } from "../types";
import { MONTHS, formatNumber } from "../utils/format";

export default function SummaryReportPage() {
  const { versions, departments, loading: refLoading } = useVersionsAndDepartments(true);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [groupBy, setGroupBy] = useState<"account" | "department">("account");
  const [departmentId, setDepartmentId] = useState<number | "">("");
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      setVersionId((versions.find((v) => v.is_default) ?? versions[0]).id);
    }
  }, [versions, versionId]);

  useEffect(() => {
    if (versionId === null) return;
    setLoading(true);
    setError(null);
    api
      .get<SummaryResponse>("/reports/summary", {
        params: { version_id: versionId, group_by: groupBy, department_id: departmentId || undefined },
      })
      .then((res) => setData(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [versionId, groupBy, departmentId]);

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
          彙總維度
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value as "account" | "department")}>
            <option value="account">依科目</option>
            <option value="department">依部門</option>
          </select>
        </label>
        <label>
          限定部門（含子部門，留白＝全部）
          <select value={departmentId} onChange={(e) => setDepartmentId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">全部</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {"　".repeat(d.level)}
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {(refLoading || loading) && <div className="page-loading">載入中…</div>}

      {data && !loading && (
        <div className="table-scroll">
          <table className="budget-grid">
            <thead>
              <tr>
                <th className="col-account">{groupBy === "account" ? "科目" : "部門"}</th>
                {MONTHS.map((m) => (
                  <th key={m}>{m} 月</th>
                ))}
                <th>合計</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.key} className={row.is_group ? "group-row" : ""}>
                  <td className="col-account" style={{ paddingLeft: `${row.level * 16 + 8}px` }}>
                    <span className="account-code">{row.code}</span> {row.name}
                  </td>
                  {MONTHS.map((m) => (
                    <td key={m} className="col-number">
                      {formatNumber(row.months[m] ?? 0)}
                    </td>
                  ))}
                  <td className="col-number row-total">{formatNumber(row.total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="col-account">月合計</td>
                {MONTHS.map((m) => (
                  <td key={m} className="col-number">
                    {formatNumber(data.month_totals[m] ?? 0)}
                  </td>
                ))}
                <td className="col-number">{formatNumber(data.grand_total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
