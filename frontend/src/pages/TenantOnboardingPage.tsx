import { useQuery } from "@tanstack/react-query";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState } from "../components/common";
import { can } from "../lib/permissions";

type Checklist = Schemas["OnboardingChecklistOut"];
type Step = Checklist["steps"][number];

/** Parcours de démarrage de la société : étapes calculées depuis l'état réel (aucun état saisi). */
export function TenantOnboardingPage() {
  const me = useMe();
  const authorized = can(me.grants, "organization.tenant.read");
  const checklist = useQuery({
    queryKey: ["tenant-onboarding"],
    enabled: authorized,
    queryFn: () => get<Checklist>("/tenant/onboarding"),
    retry: false,
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  return (
    <section>
      <h1>Démarrage</h1>
      <p className="muted">
        Progression de la mise en service de votre société. Chaque étape se coche automatiquement dès que
        l'action correspondante est réellement constatée dans l'application — rien à déclarer.
      </p>
      <DataState loading={checklist.isLoading} error={checklist.error} empty={false} emptyText="">
        {checklist.data ? <Progress checklist={checklist.data} /> : null}
      </DataState>
    </section>
  );
}

function Progress({ checklist }: { checklist: Checklist }) {
  return (
    <div>
      <p className="muted" aria-live="polite">
        {checklist.done_count}/{checklist.total} étapes réalisées ({checklist.progress_percent} %)
      </p>
      <div
        role="progressbar"
        aria-valuenow={checklist.progress_percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Progression du démarrage"
        style={{ background: "#e2e8f0", borderRadius: 4, height: 10, maxWidth: 480 }}>
        <div
          style={{
            background: "#2563eb",
            width: `${checklist.progress_percent}%`,
            height: "100%",
            borderRadius: 4,
          }}
        />
      </div>
      <ul style={{ listStyle: "none", padding: 0, maxWidth: 640 }}>
        {checklist.steps.map((step) => (
          <StepRow key={step.key} step={step} />
        ))}
      </ul>
    </div>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className="card" style={{ marginTop: 12, padding: "12px 16px" }}>
      <strong>{step.done ? "✓" : "…"} {step.label}</strong>
      <div className="muted">
        {step.hint} ({step.count}/{step.target})
      </div>
    </li>
  );
}
