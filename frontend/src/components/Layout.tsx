import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "finance_admin";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">預算編列系統</div>
        <nav className="app-nav">
          <NavLink to="/grid" className={navClass}>
            預算填報
          </NavLink>
          {isAdmin && (
            <NavLink to="/submissions" className={navClass}>
              填報進度
            </NavLink>
          )}
          <NavLink to="/reports/summary" className={navClass}>
            彙總報表
          </NavLink>
          <NavLink to="/reports/variance" className={navClass}>
            差異分析
          </NavLink>
          {isAdmin && (
            <NavLink to="/masters" className={navClass}>
              主檔維護
            </NavLink>
          )}
          {isAdmin && (
            <NavLink to="/users" className={navClass}>
              使用者管理
            </NavLink>
          )}
        </nav>
        <div className="app-user">
          <span>
            {user?.full_name}（{user?.department_name ?? "財務管理者"}）
          </span>
          <button onClick={logout}>登出</button>
        </div>
      </header>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "nav-link active" : "nav-link";
}
