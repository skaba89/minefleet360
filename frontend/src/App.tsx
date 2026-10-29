import { Navigate, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { AdminIndex, AdminLayout, AuditAdminPage, SitesAdminPage, UsersAdminPage } from "./pages/AdminPages";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { MissionDetailPage } from "./pages/MissionDetailPage";
import { MissionsPage } from "./pages/MissionsPage";
import { ReferentialsPage } from "./pages/ReferentialsPage";
import { DriverDetailPage } from "./pages/DriverDetailPage";
import { DriversPage } from "./pages/DriversPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { LiveFleetPage } from "./pages/LiveFleetPage";
import { PhoneTrackingPage } from "./pages/PhoneTrackingPage";
import { PreventivePage } from "./pages/PreventivePage";
import { ActivationPage, ResetConfirmPage, ResetRequestPage } from "./pages/PasswordPages";
import { SecurityPage } from "./pages/SecurityPage";
import { VehicleDetailPage } from "./pages/VehicleDetailPage";
import { DueDocumentsPage, RequiredDocumentsPage } from "./pages/VehicleRecords";
import { VehiclesPage } from "./pages/VehiclesPage";
import { IndicatorsPage, WeighingsPage } from "./pages/WeighingPages";
import { WorkOrderPage, WorkshopPage } from "./pages/WorkshopPages";
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
        <Route path="flotte-gps" element={<LiveFleetPage />} />
        <Route path="mon-suivi" element={<PhoneTrackingPage />} />
        <Route path="vehicules/echeances" element={<DueDocumentsPage />} />
        <Route path="vehicules/:vehicleId" element={<VehicleDetailPage />} />
        <Route path="conducteurs" element={<DriversPage />} />
        <Route path="conducteurs/:driverId" element={<DriverDetailPage />} />
        <Route path="affectations" element={<AssignmentsPage />} />
        <Route path="missions" element={<MissionsPage />} />
        <Route path="missions/:missionId" element={<MissionDetailPage />} />
        <Route path="atelier" element={<WorkshopPage />} />
        <Route path="maintenance" element={<PreventivePage />} />
        <Route path="atelier/:workOrderId" element={<WorkOrderPage />} />
        <Route path="pesees" element={<WeighingsPage />} />
        <Route path="indicateurs" element={<IndicatorsPage />} />
        <Route path="mon-compte/securite" element={<SecurityPage />} />
        <Route path="administration" element={<AdminLayout />}>
          <Route index element={<AdminIndex />} />
          <Route path="sites" element={<SitesAdminPage />} />
          <Route path="utilisateurs" element={<UsersAdminPage />} />
          <Route path="journal" element={<AuditAdminPage />} />
          <Route path="lieux-matieres" element={<ReferentialsPage />} />
          <Route path="documents-exiges" element={<RequiredDocumentsPage />} />
        </Route>
        <Route path="*" element={<p>Page introuvable.</p>} />
      </Route>
    </Routes>
  );
}
