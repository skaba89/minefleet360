import { Navigate, Route, Routes } from "react-router";

import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { OfflineNotice } from "./components/Connectivity";
import { AdminIndex, AdminLayout, AuditAdminPage, SitesAdminPage, UsersAdminPage } from "./pages/AdminPages";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { MissionDetailPage } from "./pages/MissionDetailPage";
import { MissionsPage } from "./pages/MissionsPage";
import { ReliabilityPage } from "./pages/ReliabilityPage";
import { ReferentialsPage } from "./pages/ReferentialsPage";
import { DriverDetailPage } from "./pages/DriverDetailPage";
import { DriversPage } from "./pages/DriversPage";
import { HomePage } from "./pages/HomePage";
import { ChecklistTemplatesPage, HseInspectionPage, HseInspectionsPage } from "./pages/HseInspectionsPages";
import { HseIncidentPage, HsePage } from "./pages/HsePages";
import { LoginPage } from "./pages/LoginPage";
import { LegalRegistriesPage } from "./pages/LegalRegistriesPage";
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
import { FuelPage } from "./pages/FuelPage";
import { CostsPage } from "./pages/CostsPage";
import { PartsPage } from "./pages/PartsPage";
import { TyrePage, TyresPage } from "./pages/TyresPages";
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
    <>
      <OfflineNotice />
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
          <Route path="carburant" element={<FuelPage />} />
          <Route path="pieces" element={<PartsPage />} />
          <Route path="juridique" element={<LegalRegistriesPage />} />
          <Route path="atelier/fiabilite" element={<ReliabilityPage />} />
          <Route path="atelier/:workOrderId" element={<WorkOrderPage />} />
          <Route path="hse" element={<HsePage />} />
          <Route path="hse/inspections" element={<HseInspectionsPage />} />
          <Route path="hse/inspections/:inspectionId" element={<HseInspectionPage />} />
          <Route path="hse/checklists" element={<ChecklistTemplatesPage />} />
          <Route path="hse/:incidentId" element={<HseIncidentPage />} />
          <Route path="pneus" element={<TyresPage />} />
          <Route path="pneus/:tyreId" element={<TyrePage />} />
          <Route path="couts" element={<CostsPage />} />
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
    </>
  );
}

