import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm } from "../components/forms";
import { can } from "../lib/permissions";

type Tenant = Schemas["TenantSummary"];
type TenantPage = { items: Tenant[]; page: number; page_size: number; total: number };

export function PlatformTenantsPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.list");
  const [page, setPage] = useState(1);
  const canSuspend = can(me.grants, "organization.tenant.suspend");
  const canCreate = can(me.grants, "organization.tenant.create");
  const queryClient = useQueryClient();
  const [changing, setChanging] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  const [selected, setSelected] = useState<Tenant | null>(null);

  async function changeStatus(tenant: Tenant) {
    if (!canSuspend || !selected || selected.tenant_id !== tenant.tenant_id || reason.trim().length < 3) return;
    setChanging(tenant.tenant_id);
    setActionError(null);
    try {
      const action = tenant.status === "ACTIVE" ? "suspend" : "reactivate";
      await request(`/platform/tenants/${tenant.tenant_id}/${action}`, {
        method: "POST", body: { reason: reason.trim() }, ifMatch: `"${tenant.row_version}"`,
      });
      setSelected(null);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["platform-tenants"] });
      await queryClient.invalidateQueries({ queryKey: ["platform-overview"] });
    } catch (error) {
      setActionError(error);
    } finally {
      setChanging(null);
    }
  }
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
      {canCreate && <p><Link to="/plateforme/nouvelle-societe">Créer une société cliente</Link></p>}
      {selected && (
        <form className="card form-grid" onSubmit={(event) => {
          event.preventDefault();
          void changeStatus(selected);
        }}>
          <h2>{selected.status === "ACTIVE" ? "Suspendre" : "Réactiver"} {selected.display_name}</h2>
          <p className="muted">Cette action affecte les sessions de la société. Elle sera journalisée par le serveur.</p>
          <label>Motif obligatoire
            <textarea required minLength={3} maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          {actionError !== null && <ErrorMessage error={actionError} />}
          <div className="row">
            <button type="submit" className={selected.status === "ACTIVE" ? "danger" : "primary"}
              disabled={changing !== null || reason.trim().length < 3}>
              {changing !== null ? "Traitement…" : "Confirmer"}
            </button>
            <button type="button" onClick={() => { setSelected(null); setReason(""); setActionError(null); }}>
              Annuler
            </button>
          </div>
        </form>
      )}
      <DataState loading={tenants.isLoading} error={tenants.error} empty={items.length === 0}
        emptyText="Aucune société cliente enregistrée.">
        <table>
          <thead>
            <tr><th scope="col">Code</th><th scope="col">Société</th><th scope="col">État</th><th scope="col">Environnement</th>{canSuspend && <th scope="col">Gestion</th>}</tr>
          </thead>
          <tbody>
            {items.map((tenant) => (
              <tr key={tenant.tenant_id}>
                <td>{tenant.code}</td>
                <td>{tenant.display_name}</td>
                <td>{tenant.status === "ACTIVE" ? "Active" : tenant.status === "SUSPENDED" ? "Suspendue" : tenant.status}</td>
                <td>{tenant.is_demo ? "Démonstration" : "Hors démonstration"}</td>
                {canSuspend && <td><button type="button" disabled={changing !== null || !["ACTIVE", "SUSPENDED"].includes(tenant.status)}
                  onClick={() => { setSelected(tenant); setReason(""); setActionError(null); }}>
                  {tenant.status === "ACTIVE" ? "Suspendre" : "Réactiver"}
                </button></td>}
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={20} total={tenants.data?.total ?? 0} onPage={setPage} />
      </DataState>
      <p className="muted">Les changements de statut nécessitent le droit approprié, un motif et une version de ligne à jour.</p>
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

export function PlatformCreateTenantPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.create");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    code: "", legal_name: "", display_name: "", default_timezone: "Africa/Conakry",
    admin_email: "", admin_display_name: "",
  });
  const change = (key: keyof typeof form) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  if (!authorized) {
    return <p className="error" role="alert">Création de sociétés non autorisée.</p>;
  }

  return (
    <section>
      <h1>Nouvelle société cliente</h1>
      <p className="muted">Création d'un espace indépendant et invitation du premier administrateur.
        Vérifiez l'adresse e-mail avant validation : un message d'activation est envoyé par le serveur.</p>
      <ActionForm title="Informations de la société" submitLabel="Créer et inviter"
        onSubmit={async () => {
          await request("/platform/tenants", {
            method: "POST",
            body: {
              code: form.code.trim(), legal_name: form.legal_name.trim(),
              display_name: form.display_name.trim(), default_timezone: form.default_timezone,
              admin_email: form.admin_email.trim(), admin_display_name: form.admin_display_name.trim(),
            },
          });
          await queryClient.invalidateQueries({ queryKey: ["platform-tenants"] });
          await queryClient.invalidateQueries({ queryKey: ["platform-overview"] });
        }}
        onDone={() => navigate("/plateforme/societes")}
        onCancel={() => navigate("/plateforme/societes")}>
        <label>Code unique (minuscules et tirets)
          <input required pattern="[a-z0-9-]{3,32}" maxLength={32} value={form.code} onChange={change("code")} />
        </label>
        <label>Raison sociale
          <input required minLength={2} maxLength={200} value={form.legal_name} onChange={change("legal_name")} />
        </label>
        <label>Nom affiché
          <input required minLength={2} maxLength={100} value={form.display_name} onChange={change("display_name")} />
        </label>
        <label>Fuseau horaire
          <select value={form.default_timezone} onChange={change("default_timezone")}>
            <option value="Africa/Conakry">Africa/Conakry</option>
            <option value="Africa/Abidjan">Africa/Abidjan</option>
            <option value="Africa/Dakar">Africa/Dakar</option>
            <option value="Africa/Bamako">Africa/Bamako</option>
            <option value="Europe/Paris">Europe/Paris</option>
          </select>
        </label>
        <label>E-mail du premier administrateur
          <input type="email" required value={form.admin_email} onChange={change("admin_email")} />
        </label>
        <label>Nom du premier administrateur
          <input required minLength={2} maxLength={100} value={form.admin_display_name} onChange={change("admin_display_name")} />
        </label>
      </ActionForm>
    </section>
  );
}

export function PlatformHealthPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.list");
  const probes = useQuery({
    queryKey: ["platform-health"],
    enabled: authorized,
    refetchInterval: 30_000,
    queryFn: async () => {
      const [health, ready] = await Promise.all([
        get<{ status: string }>("/health"),
        get<{ status: string }>("/ready"),
      ]);
      return { health: health.status === "ok", ready: ready.status === "ok" };
    },
  });
  if (!authorized) return <p className="error" role="alert">Accès plateforme non autorisé.</p>;
  return (
    <section>
      <h1>État des services</h1>
      <p className="muted">Sondes API vérifiées toutes les 30 secondes. Elles ne remplacent pas
        les alertes d'exploitation, les sauvegardes ni les mesures de performance.</p>
      <DataState loading={probes.isLoading} error={probes.error} empty={false}>
        <div className="tiles">
          <div className="tile">
            <strong>API : {probes.data?.health ? "Disponible" : "Indisponible"}</strong>
          </div>
          <div className="tile">
            <strong>Base et dépendances : {probes.data?.ready ? "Prêtes" : "Non prêtes"}</strong>
          </div>
        </div>
      </DataState>
      <button type="button" onClick={() => void probes.refetch()} disabled={probes.isFetching}>
        Actualiser les sondes
      </button>
    </section>
  );
}
