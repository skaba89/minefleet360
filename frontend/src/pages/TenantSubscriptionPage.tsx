import { useQuery } from "@tanstack/react-query";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState } from "../components/common";
import { Fact } from "../components/forms";
import { can } from "../lib/permissions";

type OwnSubscription = Schemas["TenantSubscriptionOut"];

const STATUS_LABEL: Record<string, string> = {
  TRIAL: "Essai",
  ACTIVE: "Actif",
  SUSPENDED: "Suspendu",
  EXPIRED: "Essai expiré",
};

function quotaText(value: number | null | undefined): string {
  return value === null || value === undefined ? "Illimité" : String(value);
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("fr-FR") : "—";
}

/** Abonnement de la société : plan souscrit, statut, échéances et quotas associés (lecture seule). */
export function TenantSubscriptionPage() {
  const me = useMe();
  const authorized = can(me.grants, "billing.subscription.read");
  const subscription = useQuery({
    queryKey: ["own-subscription"],
    enabled: authorized,
    queryFn: () => get<OwnSubscription>("/tenant/subscription"),
    retry: false,
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  return (
    <section>
      <h1>Abonnement</h1>
      <p className="muted">
        Formule souscrite par votre société et limites associées. Le renouvellement et les changements de formule
        sont gérés avec l'équipe MineFleet 360.
      </p>
      <DataState
        loading={subscription.isLoading}
        error={subscription.error}
        empty={false}
        emptyText="">
        {subscription.data ? (
          <dl className="card">
            <Fact label="Formule">{subscription.data.plan.name} ({subscription.data.plan.code})</Fact>
            <Fact label="Statut">
              {STATUS_LABEL[subscription.data.effective_status] ?? subscription.data.effective_status}
              {subscription.data.effective_status !== subscription.data.status && " (statut enregistré : "
                + (STATUS_LABEL[subscription.data.status] ?? subscription.data.status) + ")"}
            </Fact>
            <Fact label="Fin de l'essai">{formatDate(subscription.data.trial_ends_at)}</Fact>
            <Fact label="Fin de la période">{formatDate(subscription.data.period_ends_at)}</Fact>
            <Fact label="Utilisateurs">{quotaText(subscription.data.plan.max_users)}</Fact>
            <Fact label="Sites">{quotaText(subscription.data.plan.max_sites)}</Fact>
            <Fact label="Véhicules">{quotaText(subscription.data.plan.max_vehicles)}</Fact>
            <Fact label="Traceurs GPS">{quotaText(subscription.data.plan.max_gps_trackers)}</Fact>
            <Fact label="Rétention des documents">{quotaText(subscription.data.plan.document_retention_days)} jours</Fact>
          </dl>
        ) : null}
      </DataState>
      <p className="muted">
        Les limites s'appliqueront au provisionnement (utilisateurs, sites, véhicules, traceurs GPS) à mesure de
        leur mise en service technique.
      </p>
    </section>
  );
}
