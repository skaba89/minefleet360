import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, Pager } from "../components/common";
import { can } from "../lib/permissions";

type Tenant = Schemas["TenantSummary"];
type TenantPage = { items: Tenant[]; page: number; page_size: number; total: number };

export function PlatformTenantsPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.list");
  const [page, setPage] = useState(1);
  const tenants = useQuery({
    queryKey: ["platform-tenants", page],
    enabled: authorized,
    queryFn: () => get<TenantPage>("/platform/tenants", { page, page_size: 20 }),
  });

  if (!authorized) {
    return <p className="error" role="alert">Accès réservé à l'administration de la plateforme.</p>;
  }

  const items = tenants.data?.items ?? [];
  return (
    <section>
      <h1>Sociétés clientes</h1>
      <p className="muted">
        Vue de gestion de la plateforme : aucune donnée GPS, RH ou métier des sociétés n'est exposée.
      </p>
      <DataState loading={tenants.isLoading} error={tenants.error} empty={items.length === 0}
        emptyText="Aucune société cliente enregistrée.">
        <table>
          <thead>
            <tr><th scope="col">Code</th><th scope="col">Société</th><th scope="col">État</th><th scope="col">Environnement</th></tr>
          </thead>
          <tbody>
            {items.map((tenant) => (
              <tr key={tenant.tenant_id}>
                <td>{tenant.code}</td>
                <td>{tenant.display_name}</td>
                <td>{tenant.status === "ACTIVE" ? "Active" : tenant.status === "SUSPENDED" ? "Suspendue" : tenant.status}</td>
                <td>{tenant.is_demo ? "Démonstration" : "Hors démonstration"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={20} total={tenants.data?.total ?? 0} onPage={setPage} />
      </DataState>
      <p className="muted">Les opérations sensibles de suspension et de réactivation restent accessibles uniquement via les procédures autorisées.</p>
    </section>
  );
}

export function PlatformOverview() {
  const me = useMe();
  const allowed = can(me.grants, "organization.tenant.list");
  const overview = useQuery({
    queryKey: ["platform-overview"],
    enabled: allowed,
    queryFn: () => get<TenantPage>("/platform/tenants", { page: 1, page_size: 1 }),
  });
  if (!allowed) return <p className="error" role="alert">Accès plateforme non autorisé.</p>;

  return (
    <section>
      <h1>Administration de MineFleet 360</h1>
      <p className="muted">Gestion des clients et suivi de la plateforme, sans accès aux opérations privées des sociétés.</p>
      <DataState loading={overview.isLoading} error={overview.error} empty={false}>
        <div className="tiles">
          <Link className="tile" to="/plateforme/societes">
            <strong>{overview.data?.total ?? 0}</strong> société(s) cliente(s)
            <span>Consulter le registre des sociétés</span>
          </Link>
        </div>
      </DataState>
      <p>Pour consulter la flotte, les missions et le GPS, connectez-vous à l'espace de votre société avec un compte autorisé.</p>
    </section>
  );
}
