import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute, AdminRoute } from "./components/ProtectedRoute";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import BudgetGridPage from "./pages/BudgetGridPage";
import SubmissionsPage from "./pages/SubmissionsPage";
import SummaryReportPage from "./pages/SummaryReportPage";
import VarianceReportPage from "./pages/VarianceReportPage";
import MastersPage from "./pages/MastersPage";
import UsersPage from "./pages/UsersPage";

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<Navigate to="/grid" replace />} />
              <Route path="/grid" element={<BudgetGridPage />} />
              <Route path="/reports/summary" element={<SummaryReportPage />} />
              <Route path="/reports/variance" element={<VarianceReportPage />} />
              <Route element={<AdminRoute />}>
                <Route path="/submissions" element={<SubmissionsPage />} />
                <Route path="/masters" element={<MastersPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
