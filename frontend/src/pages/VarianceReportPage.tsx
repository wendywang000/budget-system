import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { VarianceResponse } from "../types";
import { formatNumber, formatPercent } from "../utils/format";

export default function VarianceReportPage() {
  const { versions, departments, loading: refLoading } = useVersionsAndDepartments(true);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [groupBy, setGroupBy] = useState<"account" | "department">("account");
  const [departmentId, setDepartmentId] = useState<number | "">("");
  const [throughMonth, setThroughMonth] = useState(new Date().getMonth() + 1);
  const [data, setData] = useState<VarianceResponse | null>(null);
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
      .get<VarianceResponse>("/reports/variance", {
        params: {
          version_id: versionId,
          group_by: groupBy,
          department_id: departmentId || undefined,
          through_month: throughMonth,
        },
      })
      .then((res) => setData(res.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [versionId, groupBy, departmentId, throughMonth]);

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
          限定部門
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
        <label>
          累計至
          <select value={throughMonth} onChange={(e) => setThroughMonth(Number(e.target.value))}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {m} 月
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {(refLoading || loading) && <div className="page-loading">載入中…</div>}

      {data && !loading && (
        <div className="table-scroll">
          <table className="plain-table variance-table">
            <thead>
              <tr>
                <th className="col-account">{groupBy === "account" ? "科目" : "部門"}</th>
                <th>全年預算</th>
                <th>全年實際</th>
                <th>全年差異</th>
                <th>累計預算（至 {data.through_month} 月）</th>
                <th>累計實際</th>
                <th>累計差異</th>
                <th>達成率</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.key} className={row.is_group ? "group-row" : ""}>
                  <td className="col-account" style={{ paddingLeft: `${row.level * 16 + 8}px` }}>
                    <span className="account-code">{row.code}</span> {row.name}
                  </td>
                  <td className="col-number">{formatNumber(row.budget)}</td>
                  <td className="col-number">{formatNumber(row.actual)}</td>
                  <td className={`col-number ${varianceClass(row.variance)}`}>{formatNumber(row.variance)}</td>
                  <td className="col-number">{formatNumber(row.budget_ytd)}</td>
                  <td className="col-number">{formatNumber(row.actual_ytd)}</td>
                  <td className={`col-number ${varianceClass(row.variance_ytd)}`}>{formatNumber(row.variance_ytd)}</td>
                  <td className="col-number">{formatPercent(row.achievement)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className="col-account">合計</td>
                <td className="col-number">{formatNumber(data.totals.budget)}</td>
                <td className="col-number">{formatNumber(data.totals.actual)}</td>
                <td className={`col-number ${varianceClass(data.totals.variance)}`}>
                  {formatNumber(data.totals.variance)}
                </td>
                <td className="col-number">{formatNumber(data.totals.budget_ytd)}</td>
                <td className="col-number">{formatNumber(data.totals.actual_ytd)}</td>
                <td className={`col-number ${varianceClass(data.totals.variance_ytd)}`}>
                  {formatNumber(data.totals.variance_ytd)}
                </td>
                <td className="col-number">{formatPercent(data.totals.achievement)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

function varianceClass(value: number): string {
  if (value > 0) return "variance-over";
  if (value < 0) return "variance-under";
  return "";
}
