import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState, Pager } from "../components/common";
import { ActionForm } from "../components/forms";
import { can } from "../lib/permissions";

type Plan = Schemas["PlanSummary"];
type PlanPage = { items: Plan[]; page: number; page_size: number; total: number };

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Brouillon",
  ACTIVE: "Actif",
  RETIRED: "Retiré",
};

function quotaText(value: number | null | undefined): string {
  return value === null || value === undefined ? "Illimité" : String(value);
}

type PlanFormState = {
  name: string;
  max_users: string;
  max_sites: string;
  max_vehicles: string;
  max_gps_trackers: string;
  document_retention_days: string;
  status: string;
};

const EMPTY_FORM: PlanFormState = {
  name: "",
  max_users: "",
  max_sites: "",
  max_vehicles: "",
  max_gps_trackers: "",
  document_retention_days: "",
  status: "DRAFT",
};

function formFromPlan(plan: Plan): PlanFormState {
  return {
    name: plan.name,
    max_users: plan.max_users?.toString() ?? "",
    max_sites: plan.max_sites?.toString() ?? "",
    max_vehicles: plan.max_vehicles?.toString() ?? "",
    max_gps_trackers: plan.max_gps_trackers?.toString() ?? "",
    document_retention_days: plan.document_retention_days?.toString() ?? "",
    status: plan.status,
  };
}

/** Quota saisi vide = NULL côté API = illimité. */
function quotaValue(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : Number(trimmed);
}

function PlanEditForm({ plan, onDone }: { plan: Plan; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanFormState>(() => formFromPlan(plan));
  const change = (key: keyof PlanFormState) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <ActionForm
      title={`Modifier le plan ${plan.code}`}
      submitLabel="Enregistrer"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        await request(`/platform/saas-plans/${plan.plan_id}`, {
          method: "PATCH",
          body: {
            name: form.name.trim(),
            status: form.status,
            max_users: quotaValue(form.max_users),
            max_sites: quotaValue(form.max_sites),
            max_vehicles: quotaValue(form.max_vehicles),
            max_gps_trackers: quotaValue(form.max_gps_trackers),
            document_retention_days: quotaValue(form.document_retention_days),
          },
          ifMatch: `"${plan.row_version}"`,
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-plans"] });
      }}>
      <label>Nom affiché
        <input required minLength={2} maxLength={80} value={form.name} onChange={change("name")} />
      </label>
      <label>Quota utilisateurs (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_users} onChange={change("max_users")} />
      </label>
      <label>Quota sites (vide = illimité)
        <input type="number" min={1} max={10000} value={form.max_sites} onChange={change("max_sites")} />
      </label>
      <label>Quota véhicules (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_vehicles} onChange={change("max_vehicles")} />
      </label>
      <label>Quota traceurs GPS (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_gps_trackers} onChange={change("max_gps_trackers")} />
      </label>
      <label>Rétention des documents en jours (vide = illimité)
        <input
          type="number" min={30} max={3650} value={form.document_retention_days}
          onChange={change("document_retention_days")}
        />
      </label>
      <label>Statut
        <select value={form.status} onChange={change("status")}>
          <option value="DRAFT">Brouillon</option>
          <option value="ACTIVE">Actif</option>
          <option value="RETIRED">Retiré (définitif)</option>
        </select>
      </label>
    </ActionForm>
  );
}

function CreatePlanForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PlanFormState>({ ...EMPTY_FORM });
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const change = (key: keyof PlanFormState) => (event: { target: { value: string } }) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  return (
    <ActionForm
      title="Créer un plan SaaS"
      submitLabel="Créer"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        await request("/platform/saas-plans", {
          method: "POST",
          body: {
            code: code.trim(),
            name: form.name.trim(),
            description: description.trim() === "" ? null : description.trim(),
            status: form.status,
            max_users: quotaValue(form.max_users),
            max_sites: quotaValue(form.max_sites),
            max_vehicles: quotaValue(form.max_vehicles),
            max_gps_trackers: quotaValue(form.max_gps_trackers),
            document_retention_days: quotaValue(form.document_retention_days),
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-plans"] });
      }}>
      <label>Code (majuscules, chiffres, tiret bas)
        <input
          required pattern="[A-Z][A-Z0-9_]{1,29}" maxLength={30} value={code}
          onChange={(event) => setCode(event.target.value)}
        />
      </label>
      <label>Nom affiché
        <input required minLength={2} maxLength={80} value={form.name} onChange={change("name")} />
      </label>
      <label>Description
        <textarea maxLength={500} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <label>Quota utilisateurs (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_users} onChange={change("max_users")} />
      </label>
      <label>Quota sites (vide = illimité)
        <input type="number" min={1} max={10000} value={form.max_sites} onChange={change("max_sites")} />
      </label>
      <label>Quota véhicules (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_vehicles} onChange={change("max_vehicles")} />
      </label>
      <label>Quota traceurs GPS (vide = illimité)
        <input type="number" min={1} max={100000} value={form.max_gps_trackers} onChange={change("max_gps_trackers")} />
      </label>
      <label>Rétention des documents en jours (vide = illimité)
        <input
          type="number" min={30} max={3650} value={form.document_retention_days}
          onChange={change("document_retention_days")}
        />
      </label>
      <label>Statut
        <select value={form.status} onChange={change("status")}>
          <option value="DRAFT">Brouillon</option>
          <option value="ACTIVE">Actif</option>
        </select>
      </label>
    </ActionForm>
  );
}

/** Catalogue des plans SaaS — lot 1 commercialisation (référentiel plateforme, pas de tarif). */
export function PlatformPlansPage() {
  const me = useMe();
  const authorized = can(me.grants, "billing.plan.list");
  const canCreate = can(me.grants, "billing.plan.create");
  const canUpdate = can(me.grants, "billing.plan.update");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Plan | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const plans = useQuery({
    queryKey: ["saas-plans", page],
    enabled: authorized,
    queryFn: () => get<PlanPage>("/platform/saas-plans", { page, page_size: 20 }),
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  const items = plans.data?.items ?? [];
  return (
    <section>
      <h1>Plans SaaS</h1>
      <p className="muted">
        Catalogue de l'offre et quotas associés (référentiel plateforme). L'abonnement des sociétés et la
        facturation sont des lots ultérieurs : aucun tarif ni moyen de paiement n'est géré ici.
      </p>
      {canCreate && (
        <p>
          <button type="button" className="primary" onClick={() => { setShowCreate(true); setSelected(null); }}>
            Créer un plan
          </button>
        </p>
      )}
      {showCreate && canCreate && <CreatePlanForm onDone={() => setShowCreate(false)} />}
      {selected && canUpdate && <PlanEditForm plan={selected} onDone={() => setSelected(null)} />}
      <DataState
        loading={plans.isLoading}
        error={plans.error}
        empty={items.length === 0}
        emptyText="Aucun plan défini.">
        <table>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Nom</th>
              <th scope="col">Statut</th>
              <th scope="col">Utilisateurs</th>
              <th scope="col">Sites</th>
              <th scope="col">Véhicules</th>
              <th scope="col">Traceurs GPS</th>
              <th scope="col">Rétention (j)</th>
              {canUpdate && <th scope="col">Gestion</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((plan) => (
              <tr key={plan.plan_id}>
                <td>{plan.code}</td>
                <td>{plan.name}</td>
                <td>{STATUS_LABEL[plan.status] ?? plan.status}</td>
                <td>{quotaText(plan.max_users)}</td>
                <td>{quotaText(plan.max_sites)}</td>
                <td>{quotaText(plan.max_vehicles)}</td>
                <td>{quotaText(plan.max_gps_trackers)}</td>
                <td>{quotaText(plan.document_retention_days)}</td>
                {canUpdate && (
                  <td>
                    <button
                      type="button"
                      disabled={plan.status === "RETIRED"}
                      onClick={() => { setSelected(plan); setShowCreate(false); }}>
                      Modifier
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={20} total={plans.data?.total ?? 0} onPage={setPage} />
      </DataState>
      <p className="muted">
        Tout changement est journalisé par le serveur. « Retiré » est définitif : le plan reste consultable pour
        l'historique mais ne peut plus être modifié ni réactivé.
      </p>
    </section>
  );
}
