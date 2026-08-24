import { FormEvent, useEffect, useState } from "react";
import { api, apiErrorMessage } from "../../api/client";
import type { BudgetVersion, VersionStatus } from "../../types";
import { VERSION_STATUS_LABELS } from "../../types";

const STATUS_OPTIONS: VersionStatus[] = ["draft", "open", "locked"];

const emptyForm = {
  fiscal_year: new Date().getFullYear(),
  name: "",
  status: "open" as VersionStatus,
  is_default: false,
  description: "",
  copy_from_version_id: "" as number | "",
  copy_ratio: 1,
};

export default function VersionsTab() {
  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<BudgetVersion[]>("/versions");
      setVersions(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    try {
      await api.post("/versions", {
        fiscal_year: form.fiscal_year,
        name: form.name,
        status: form.status,
        is_default: form.is_default,
        description: form.description || null,
        copy_from_version_id: form.copy_from_version_id === "" ? null : Number(form.copy_from_version_id),
        copy_ratio: form.copy_ratio,
      });
      setMessage("已新增版本");
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function changeStatus(version: BudgetVersion, status: VersionStatus) {
    setError(null);
    try {
      await api.patch(`/versions/${version.id}`, { status });
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function setDefault(version: BudgetVersion) {
    setError(null);
    try {
      await api.patch(`/versions/${version.id}`, { is_default: true });
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleDelete(version: BudgetVersion) {
    if (!window.confirm(`確定要刪除版本「${version.fiscal_year} ${version.name}」及其所有預算明細嗎？`)) return;
    setError(null);
    try {
      await api.delete(`/versions/${version.id}`);
      await load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="masters-tab">
      <form className="masters-form" onSubmit={handleSubmit}>
        <h3>新增預算版本</h3>
        <div className="form-grid">
          <label>
            年度
            <input
              type="number"
              value={form.fiscal_year}
              onChange={(e) => setForm({ ...form, fiscal_year: Number(e.target.value) })}
              required
            />
          </label>
          <label>
            版本名稱
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="例如：初版、修正版"
              required
            />
          </label>
          <label>
            狀態
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as VersionStatus })}>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {VERSION_STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
            />
            設為預設版本
          </label>
          <label>
            從既有版本複製（可留白）
            <select
              value={form.copy_from_version_id}
              onChange={(e) =>
                setForm({ ...form, copy_from_version_id: e.target.value ? Number(e.target.value) : "" })
              }
            >
              <option value="">（不複製）</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.fiscal_year} - {v.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            複製倍率
            <input
              type="number"
              step="0.01"
              value={form.copy_ratio}
              onChange={(e) => setForm({ ...form, copy_ratio: Number(e.target.value) })}
            />
          </label>
          <label className="wide-field">
            說明
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
        </div>
        <div className="form-actions">
          <button type="submit">新增版本</button>
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
              <th>年度</th>
              <th>名稱</th>
              <th>狀態</th>
              <th>預設</th>
              <th>說明</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td>{v.fiscal_year}</td>
                <td>{v.name}</td>
                <td>
                  <select value={v.status} onChange={(e) => changeStatus(v, e.target.value as VersionStatus)}>
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {VERSION_STATUS_LABELS[s]}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{v.is_default ? "★" : <button onClick={() => setDefault(v)}>設為預設</button>}</td>
                <td>{v.description ?? ""}</td>
                <td className="action-cell">
                  <button onClick={() => handleDelete(v)}>刪除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
