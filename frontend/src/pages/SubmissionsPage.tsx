import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "../api/client";
import { useVersionsAndDepartments } from "../hooks/useVersionsAndDepartments";
import type { SubmissionOut } from "../types";
import { SUBMISSION_STATUS_LABELS } from "../types";
import { formatNumber } from "../utils/format";

export default function SubmissionsPage() {
  const { versions, loading: refLoading } = useVersionsAndDepartments(false);
  const [versionId, setVersionId] = useState<number | null>(null);
  const [rows, setRows] = useState<SubmissionOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [commentDraft, setCommentDraft] = useState<Record<number, string>>({});

  useEffect(() => {
    if (versionId === null && versions.length > 0) {
      setVersionId((versions.find((v) => v.is_default) ?? versions[0]).id);
    }
  }, [versions, versionId]);

  async function load() {
    if (versionId === null) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<SubmissionOut[]>("/budget/submissions", { params: { version_id: versionId } });
      setRows(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId]);

  async function act(row: SubmissionOut, action: "approve" | "return") {
    if (versionId === null) return;
    setError(null);
    setMessage(null);
    try {
      await api.post(`/budget/${action}`, {
        version_id: versionId,
        department_id: row.department_id,
        comment: commentDraft[row.department_id] ?? null,
      });
      setMessage(action === "approve" ? `已核定 ${row.department_name}` : `已退回 ${row.department_name}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const totalAmount = rows.reduce((sum, r) => sum + r.total, 0);

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
      </div>

      {error && <div className="banner banner-error">{error}</div>}
      {message && <div className="banner banner-info">{message}</div>}
      {(refLoading || loading) && <div className="page-loading">載入中…</div>}

      {!loading && (
        <div className="table-scroll">
          <table className="plain-table">
            <thead>
              <tr>
                <th>部門代號</th>
                <th>部門名稱</th>
                <th>狀態</th>
                <th>金額合計</th>
                <th>送出時間</th>
                <th>審核意見</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.department_id}>
                  <td>{row.department_code}</td>
                  <td>{row.department_name}</td>
                  <td>
                    <span className={`status-pill status-${row.status}`}>
                      {SUBMISSION_STATUS_LABELS[row.status]}
                    </span>
                  </td>
                  <td className="col-number">{formatNumber(row.total)}</td>
                  <td>{row.submitted_at ? new Date(row.submitted_at).toLocaleString("zh-TW") : "—"}</td>
                  <td>
                    <input
                      type="text"
                      placeholder="填寫審核意見（退回時建議填寫）"
                      value={commentDraft[row.department_id] ?? row.comment ?? ""}
                      onChange={(e) =>
                        setCommentDraft((prev) => ({ ...prev, [row.department_id]: e.target.value }))
                      }
                    />
                  </td>
                  <td className="action-cell">
                    <button
                      disabled={row.status !== "submitted"}
                      onClick={() => act(row, "approve")}
                    >
                      核定
                    </button>
                    <button
                      disabled={row.status !== "submitted"}
                      onClick={() => act(row, "return")}
                    >
                      退回
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>合計</td>
                <td className="col-number">{formatNumber(totalAmount)}</td>
                <td colSpan={3} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
