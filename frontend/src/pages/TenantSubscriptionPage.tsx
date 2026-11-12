import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { binaryRequest, get, type Schemas } from "../api/client";
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
        Ces limites sont appliquées au provisionnement : au-delà, la création d'un utilisateur, d'un site, d'un
        véhicule ou d'un traceur GPS est refusée avec un message dédié (les comptes désactivés, véhicules réformés
        et traceurs révoqués libèrent leur place). La rétention des documents s'applique aux purges automatiques.
      </p>
      <ReversibilitySection />
    </section>
  );
}

/** Réversibilité (lot 4) : export JSON des données de la société, réservé à l'administrateur. */
function ReversibilitySection() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.export");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!authorized) {
    return null;
  }
  const download = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await binaryRequest("/tenant/export");
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const match = /filename="([^"]+)"/.exec(disposition);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = match?.[1] ?? "export-minefleet.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Téléchargement impossible.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div style={{ marginTop: 24 }}>
      <h2>Réversibilité</h2>
      <p className="muted">
        Téléchargez les données de votre société (sites, utilisateurs, véhicules, abonnements, factures) dans un
        fichier JSON lisible par un outil tiers. L'export ne contient aucun secret d'authentification et il est
        journalisé.
      </p>
      <button type="button" onClick={download} disabled={busy}>
        {busy ? "Export en cours…" : "Exporter les données (JSON)"}
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
