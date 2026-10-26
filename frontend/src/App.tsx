import { Navigate, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { DriversPage } from "./pages/DriversPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { ActivationPage, ResetConfirmPage, ResetRequestPage } from "./pages/PasswordPages";
import { VehiclesPage } from "./pages/VehiclesPage";
import { SiteProvider } from "./site/SiteContext";

function Protected() {
  const { status } = useAuth();
  if (status === "loading") return <p className="muted center" role="status">Chargement…</p>;
  if (status === "anonymous") return <Navigate to="/connexion" replace />;
  return (
    <SiteProvider>
      <Layout />
    </SiteProvider>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/connexion" element={<LoginPage />} />
      <Route path="/activation" element={<ActivationPage />} />
      <Route path="/reinitialisation" element={<ResetConfirmPage />} />
      <Route path="/mot-de-passe-oublie" element={<ResetRequestPage />} />
      <Route element={<Protected />}>
        <Route index element={<HomePage />} />
        <Route path="vehicules" element={<VehiclesPage />} />
        <Route path="conducteurs" element={<DriversPage />} />
        <Route path="affectations" element={<AssignmentsPage />} />
        <Route path="*" element={<p>Page introuvable.</p>} />
      </Route>
    </Routes>
  );
}
