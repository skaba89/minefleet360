import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState } from "../components/common";
import { can } from "../lib/permissions";
import { formatGnf } from "./PlatformInvoicesPage";

type Overview = Schemas["TenantOverviewOut"];
type Tenant = Schemas["TenantSummary"];
type TenantPage = { items: Tenant[]; page: number; page_size: number; total: number };

const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  SUSPENDED: "Suspendue",
  TRIAL: "Essai",
  EXPIRED: "Essai expiré",
  CANCELLED: "Annulé",
};

/** Libellés du cycle de vie d'abonnement (masculin — distinct du statut de la société). */
const SUBSCRIPTION_STATUS_LABEL: Record<string, string> = {
  TRIAL: "Essai",
  ACTIVE: "Actif",
  SUSPENDED: "Suspendu",
  CANCELLED: "Annulé",
  EXPIRED: "Essai expiré",
};

/** Libellés du statut de facture (la page mélange trois référentiels d'états). */
const INVOICE_STATUS_LABEL: Record<string, string> = {
  DRAFT: "Brouillon",
  ISSUED: "Émise",
  VOIDED: "Annulée",
};

function subscriptionStatus(status: string): string {
  return SUBSCRIPTION_STATUS_LABEL[status] ?? STATUS_LABEL[status] ?? status;
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("fr-FR") : "—";
}

/** Outillage support (lot 4) : vue consolidée d'un compte client — usage, abonnement, factures. */
export function PlatformTenantSupportPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.support");
  const [tenantId, setTenantId] = useState("");

  const tenants = useQuery({
    queryKey: ["saas-support-tenants"],
    enabled: authorized,
    queryFn: () => get<TenantPage>("/platform/tenants", { page: 1, page_size: 100 }),
    retry: false,
  });
  const overview = useQuery({
    queryKey: ["saas-support-overview", tenantId],
    enabled: authorized && tenantId !== "",
    queryFn: () => get<Overview>(`/platform/tenants/${tenantId}/overview`),
    retry: false,
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  return (
    <section>
      <h1>Support société</h1>
      <p className="muted">
        Vue consolidée d'un compte client : usage réel face aux limites du plan, abonnement courant (statut
        effectif), comptes utilisateurs et factures récentes. Calculée à la lecture — rien n'est modifié ici.
      </p>
      <p>
        <label htmlFor="support-tenant">Société</label>{" "}
        <select
          id="support-tenant"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}>
          <option value="">— choisir une société —</option>
          {(tenants.data?.items ?? []).map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.display_name} ({tenant.code})
            </option>
          ))}
        </select>
      </p>
      <DataState
        loading={overview.isLoading}
        error={overview.error}
        empty={tenantId === ""}
        emptyText="Choisissez une société pour afficher sa vue d'ensemble.">
        {overview.data ? <OverviewView overview={overview.data} /> : null}
      </DataState>
    </section>
  );
}

function OverviewView({ overview }: { overview: Overview }) {
  const subscription = overview.subscription;
  return (
    <div>
      <dl className="card">
        <dt>Société</dt>
        <dd>
          {overview.tenant.display_name} ({overview.tenant.code}) —{" "}
          {STATUS_LABEL[overview.tenant.status] ?? overview.tenant.status}
        </dd>
        <dt>Abonnement</dt>
        <dd>
          {subscription
            ? `${subscription.plan.name} — ${subscriptionStatus(subscription.effective_status)}` +
              (subscription.effective_status !== subscription.status
                ? ` (statut enregistré : ${subscriptionStatus(subscription.status)})`
                : "")
            : "Aucun abonnement"}
        </dd>
        <dt>Fin de période</dt>
        <dd>{formatDate(subscription?.period_ends_at)}</dd>
        <dt>Utilisateurs</dt>
        <dd>
          {overview.users.active} actifs, {overview.users.invited} en attente, {overview.users.disabled}{" "}
          désactivés
        </dd>
      </dl>
      <h2>Usage face aux limites du plan</h2>
      <table>
        <thead>
          <tr>
            <th>Ressource</th>
            <th>Usage</th>
            <th>Limite</th>
          </tr>
        </thead>
        <tbody>
          {overview.usage.map((row) => (
            <tr key={row.field}>
              <td>{row.label}</td>
              <td>{row.usage}</td>
              <td>{row.limit === null ? "Illimité" : row.limit}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Factures récentes</h2>
      {overview.invoices.length === 0 ? (
        <p className="muted">Aucune facture émise pour cette société.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Numéro</th>
              <th>Statut</th>
              <th>Total</th>
              <th>Créée le</th>
            </tr>
          </thead>
          <tbody>
            {overview.invoices.map((invoice) => (
              <tr key={invoice.invoice_id}>
                <td>{invoice.number}</td>
                <td>{INVOICE_STATUS_LABEL[invoice.status] ?? invoice.status}</td>
                <td>{formatGnf(invoice.total_gnf)}</td>
                <td>{formatDate(invoice.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
