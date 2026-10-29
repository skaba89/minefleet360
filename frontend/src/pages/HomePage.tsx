import { Link } from "react-router";

import { useMe } from "../auth/AuthContext";
import { can } from "../lib/permissions";
import { FleetDashboard } from "./FleetDashboard";

const ROLE_LABELS: Record<string, string> = {
  TENANT_ADMIN: "Administrateur",
  DIRECTION: "Direction",
  OPS_MANAGER: "Responsable d'exploitation",
  DISPATCHER: "Dispatcher",
  HR: "Ressources humaines",
  DRIVER: "Conducteur",
  WORKSHOP_CHIEF: "Chef d'atelier",
  MECHANIC: "Mécanicien",
  STOREKEEPER: "Magasinier",
  FUEL_MANAGER: "Responsable carburant",
  HSE: "HSE",
  FINANCE: "Finance",
  AUDITOR: "Auditeur",
};

export function HomePage() {
  const me = useMe();
  if (can(me.grants, "fleet.vehicle.read")) return <FleetDashboard />;
  return (
    <section>
      <h1>Bonjour {me.display_name}</h1>
      <p className="muted">
        Espace {me.workspace_code} — fuseau d'affichage par défaut : {me.timezone}
      </p>
      <h2>Vos rôles</h2>
      <ul>
        {me.grants.map((g) => (
          <li key={`${g.role_code}-${g.site_id ?? "tenant"}`}>
            {ROLE_LABELS[g.role_code] ?? g.role_code}
            {g.scope_type === "SITE" ? " (sur un site)" : " (toute la société)"}
          </li>
        ))}
      </ul>
      <div className="tiles">
        {can(me.grants, "assignment.vehicle_assignment.read") && (
          <Link className="tile" to="/affectations">
            Affectations conducteur ↔ véhicule
          </Link>
        )}
        {can(me.grants, "fleet.vehicle.read") && (
          <Link className="tile" to="/vehicules">
            Parc de véhicules et engins
          </Link>
        )}
        {can(me.grants, "workforce.driver.read") && (
          <Link className="tile" to="/conducteurs">
            Conducteurs
          </Link>
        )}
      </div>
    </section>
  );
}
