import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState, Pager } from "../components/common";
import { ActionForm } from "../components/forms";
import { can } from "../lib/permissions";

type Subscription = Schemas["SubscriptionSummary"];
type Tenant = Schemas["TenantSummary"];
type SubscriptionPage = { items: Subscription[]; page: number; page_size: number; total: number };

const STATUS_LABEL: Record<string, string> = {
  TRIAL: "Essai",
  ACTIVE: "Actif",
  SUSPENDED: "Suspendu",
  CANCELLED: "Annulé",
  EXPIRED: "Essai expiré",
};

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("fr-FR") : "—";
}

/** Actions du cycle de vie : activate / suspend / reactivate / cancel / renew (If-Match obligatoire). */
function SubscriptionActionForm({
  tenantId,
  subscription,
  action,
  onDone,
}: {
  tenantId: string;
  subscription: Subscription;
  action: "activate" | "suspend" | "reactivate" | "cancel" | "renew";
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const needsReason = action === "suspend" || action === "cancel";
  const titles: Record<typeof action, string> = {
    activate: `Activer l'essai de ${subscription.plan_code}`,
    suspend: `Suspendre l'abonnement ${subscription.plan_code}`,
    reactivate: `Réactiver l'abonnement ${subscription.plan_code}`,
    cancel: `Annuler l'abonnement ${subscription.plan_code}`,
    renew: `Renouveler l'abonnement ${subscription.plan_code}`,
  };

  return (
    <ActionForm
      title={titles[action]}
      submitLabel="Confirmer"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        const body = action === "renew" ? { period_ends_at: new Date(periodEnd).toISOString() } : needsReason ? { reason: reason.trim() } : {};
        await request(`/platform/tenants/${tenantId}/subscriptions/${subscription.subscription_id}/${action}`, {
          method: "POST",
          body,
          ifMatch: `"${subscription.row_version}"`,
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-subscriptions", tenantId] });
      }}>
      {needsReason && (
        <label>Motif obligatoire
          <textarea required minLength={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
      )}
      {action === "renew" && (
        <label>Nouvelle fin de période
          <input type="date" required value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
        </label>
      )}
    </ActionForm>
  );
}

function CreateSubscriptionForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [tenantId, setTenantId] = useState("");
  const [planId, setPlanId] = useState("");
  const [mode, setMode] = useState<"trial" | "direct">("trial");
  const [trialDays, setTrialDays] = useState("30");
  const [notes, setNotes] = useState("");

  const tenants = useQuery({
    queryKey: ["saas-sub-tenants"],
    enabled: true,
    queryFn: () => get<{ items: Tenant[] }>("/platform/tenants", { page: 1, page_size: 100 }),
  });
  const plans = useQuery({
    queryKey: ["saas-plans", 1],
    enabled: true,
    queryFn: () => get<{ items: Schemas["PlanSummary"][] }>("/platform/saas-plans", { page: 1, page_size: 100 }),
  });
  const activePlans = (plans.data?.items ?? []).filter((plan) => plan.status === "ACTIVE");

  return (
    <ActionForm
      title="Souscrire un abonnement"
      submitLabel="Souscrire"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        await request(`/platform/tenants/${tenantId}/subscriptions`, {
          method: "POST",
          body: {
            plan_id: planId,
            ...(mode === "trial" ? { trial_days: Number(trialDays) } : {}),
            notes: notes.trim() === "" ? null : notes.trim(),
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-subscriptions", tenantId] });
      }}>
      <label>Société cliente
        <select required value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          <option value="">— choisir —</option>
          {(tenants.data?.items ?? []).map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.code} — {tenant.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>Plan (actifs uniquement)
        <select required value={planId} onChange={(e) => setPlanId(e.target.value)}>
          <option value="">— choisir —</option>
          {activePlans.map((plan) => (
            <option key={plan.plan_id} value={plan.plan_id}>
              {plan.code} — {plan.name}
            </option>
          ))}
        </select>
      </label>
      <label>Mode
        <select value={mode} onChange={(e) => setMode(e.target.value === "trial" ? "trial" : "direct")}>
          <option value="trial">Essai daté</option>
          <option value="direct">Activation directe</option>
        </select>
      </label>
      {mode === "trial" && (
        <label>Durée de l'essai (jours)
          <input type="number" min={1} max={365} required value={trialDays} onChange={(e) => setTrialDays(e.target.value)} />
        </label>
      )}
      <label>Notes (facultatif)
        <textarea maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
    </ActionForm>
  );
}

/** Abonnements des sociétés — lot 2 commercialisation (cycle de vie plateforme). */
export function PlatformSubscriptionsPage() {
  const me = useMe();
  const authorized = can(me.grants, "billing.subscription.manage");
  const [tenantId, setTenantId] = useState("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<{ subscription: Subscription; action: "activate" | "suspend" | "reactivate" | "cancel" | "renew" } | null>(null);

  const tenants = useQuery({
    queryKey: ["saas-sub-tenants"],
    enabled: authorized,
    queryFn: () => get<{ items: Tenant[] }>("/platform/tenants", { page: 1, page_size: 100 }),
  });
  const subscriptions = useQuery({
    queryKey: ["saas-subscriptions", tenantId, page],
    enabled: authorized && tenantId !== "",
    queryFn: () => get<SubscriptionPage>(`/platform/tenants/${tenantId}/subscriptions`, { page, page_size: 20 }),
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  const items = subscriptions.data?.items ?? [];
  const actionsFor = (subscription: Subscription) => {
    const actions: Array<"activate" | "suspend" | "reactivate" | "cancel" | "renew"> = [];
    if (subscription.status === "TRIAL") actions.push("activate", "suspend", "cancel");
    if (subscription.status === "ACTIVE") actions.push("suspend", "cancel", "renew");
    if (subscription.status === "SUSPENDED") actions.push("reactivate", "cancel");
    return actions;
  };

  return (
    <section>
      <h1>Abonnements SaaS</h1>
      <p className="muted">
        Cycle de vie des abonnements des sociétés : essai daté, activation, suspension avec motif, annulation
        définitive, renouvellement manuel de la période. Un seul abonnement vivant par société — la souscription
        d'un nouvel abonnement annule l'ancien (historique conservé). Aucun tarif ni paiement à ce stade.
      </p>
      <p>
        <button type="button" className="primary" onClick={() => setShowCreate(true)}>
          Souscrire un abonnement
        </button>
      </p>
      {showCreate && <CreateSubscriptionForm onDone={() => setShowCreate(false)} />}
      {selected && (
        <SubscriptionActionForm
          tenantId={tenantId}
          subscription={selected.subscription}
          action={selected.action}
          onDone={() => setSelected(null)}
        />
      )}
      <label>Société
        <select value={tenantId} onChange={(e) => { setTenantId(e.target.value); setPage(1); setSelected(null); }}>
          <option value="">— choisir une société —</option>
          {(tenants.data?.items ?? []).map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.code} — {tenant.display_name}
            </option>
          ))}
        </select>
      </label>
      {tenantId !== "" && (
        <DataState
          loading={subscriptions.isLoading}
          error={subscriptions.error}
          empty={items.length === 0}
          emptyText="Aucun abonnement pour cette société.">
          <table>
            <thead>
              <tr>
                <th scope="col">Plan</th>
                <th scope="col">Statut</th>
                <th scope="col">Statut enregistré</th>
                <th scope="col">Fin d'essai</th>
                <th scope="col">Fin de période</th>
                <th scope="col">Motif de suspension</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((subscription) => (
                <tr key={subscription.subscription_id}>
                  <td>{subscription.plan_code} — {subscription.plan_name}</td>
                  <td>{STATUS_LABEL[subscription.effective_status] ?? subscription.effective_status}</td>
                  <td>{STATUS_LABEL[subscription.status] ?? subscription.status}</td>
                  <td>{formatDate(subscription.trial_ends_at)}</td>
                  <td>{formatDate(subscription.period_ends_at)}</td>
                  <td>{subscription.suspension_reason ?? "—"}</td>
                  <td>
                    {actionsFor(subscription).map((action) => (
                      <button
                        key={action}
                        type="button"
                        onClick={() => { setSelected({ subscription, action }); setShowCreate(false); }}>
                        {action === "activate" && "Activer"}
                        {action === "suspend" && "Suspendre"}
                        {action === "reactivate" && "Réactiver"}
                        {action === "cancel" && "Annuler"}
                        {action === "renew" && "Renouveler"}
                      </button>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} pageSize={20} total={subscriptions.data?.total ?? 0} onPage={setPage} />
        </DataState>
      )}
      <p className="muted">
        Chaque transition est journalisée par le serveur avec son motif. Les sessions des utilisateurs ne sont pas
        affectées par une suspension d'abonnement (contrairement à la suspension de société).
      </p>
    </section>
  );
}
