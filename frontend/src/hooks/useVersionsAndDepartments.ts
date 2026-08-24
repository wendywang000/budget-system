import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { BudgetVersion, Department } from "../types";

/** 共用的「版本清單 + 可存取部門清單」載入邏輯,供填報表、報表頁使用。 */
export function useVersionsAndDepartments(accessibleOnly: boolean) {
  const [versions, setVersions] = useState<BudgetVersion[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      api.get<BudgetVersion[]>("/versions"),
      api.get<Department[]>("/departments", { params: { accessible_only: accessibleOnly } }),
    ])
      .then(([vRes, dRes]) => {
        if (!mounted) return;
        setVersions(vRes.data);
        setDepartments(dRes.data);
        setError(null);
      })
      .catch((err) => mounted && setError(String(err)))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [accessibleOnly]);

  return { versions, departments, loading, error };
}
