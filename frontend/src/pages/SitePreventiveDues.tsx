import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";
import { formatDate } from "../lib/time";
import { TRIGGER_LABEL } from "./VehiclePreventiveDues";

type SiteDue = Schemas["SiteDueOut"];
type Evaluation = Schemas["PreventiveEvaluationOut"];

const STATUS_LABEL: Record<SiteDue["status"], string> = {
  DUE: "Due",
  SCHEDULED: "OT planifié",
  COMPLETED: "Terminée",
  CANCELLED: "Annulée",
};

/** Échéances enregistrées du site (ou de tous les sites autorisés) et bouton « Évaluer les échéances ». */
export function SitePreventiveDues({ siteId }: { siteId: string | null }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const allowed = can(me.grants, "maintenance.preventive.read", siteId);
  const managing = can(me.grants, "maintenance.preventive.manage", siteId);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<Evaluation | null>(null);
  const queryKey = ["site-preventive-dues", siteId];
  const dues = useQuery({
    queryKey,
    queryFn: () =>
      get<{ items: SiteDue[]; total: number }>("/preventive-dues", {
        site_id: siteId,
        open_only: true,
        page_size: 200,
      }),
    enabled: allowed,
  });

  if (!allowed) return null;

  async function act(key: string, action: () => Promise<unknown>) {
    setBusy(key);
    setError(null);
    try {
      await action();
      await queryClient.invalidateQueries({ queryKey });
      await queryClient.invalidateQueries({ queryKey: ["preventive-dues"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(null);
    }
  }

  function evaluate() {
    setResult(null);
    void act("evaluate", async () => {
      const response = await request<Evaluation>("/preventive-dues/evaluate", { method: "POST", body: { site_id: siteId } });
      setResult(response.data);
    });
  }

  function schedule(dueId: string) {
    void act(dueId, () => request(`/preventive-dues/${dueId}/schedule`, { method: "POST" }));
  }

  return (
    <section className="card" aria-label="Échéances préventives du site">
      <div className="page-head">
        <h2>Échéances à traiter{siteId ? "" : " (tous mes sites)"}</h2>
        {managing && (
          <button type="button" className="primary" disabled={busy !== null} onClick={evaluate}>
            {busy === "evaluate" ? "Évaluation…" : "Évaluer les échéances"}
          </button>
        )}
      </div>
      {result && (
        <p role="status">
          {result.plans_evaluated} plan(s) évalué(s) : {result.created} nouvelle(s) échéance(s),{" "}
          {result.already_recorded} déjà enregistrée(s), {result.upcoming} à venir,{" "}
          {result.insufficient_data} en information insuffisante (déclarez leur dernier entretien).
        </p>
      )}
      {error != null && <ErrorMessage error={error} />}
      <DataState loading={dues.isLoading} error={dues.error} empty={!dues.data?.items.length} emptyText="Aucune échéance due ou planifiée.">
        <table>
          <thead>
            <tr>
              <th scope="col">Engin</th>
              <th scope="col">Plan</th>
              <th scope="col">Déclencheur</th>
              <th scope="col">Échéance</th>
              <th scope="col">Statut</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {(dues.data?.items ?? []).map((due) => (
              <tr key={due.maintenance_due_id}>
                <td>
                  <Link to={`/vehicules/${due.vehicle_id}`}>{due.fleet_number}</Link>
                </td>
                <td>{due.plan_code}</td>
                <td>{TRIGGER_LABEL[due.trigger_kind]}</td>
                <td>{due.due_on ? formatDate(due.due_on) : due.due_meter == null ? "—" : String(due.due_meter)}</td>
                <td>{STATUS_LABEL[due.status]}</td>
                <td>
                  {due.work_order_id ? (
                    <Link to={`/atelier/${due.work_order_id}`}>Voir l'OT</Link>
                  ) : (
                    managing &&
                    due.status === "DUE" && (
                      <button type="button" disabled={busy !== null} onClick={() => schedule(due.maintenance_due_id)}>
                        {busy === due.maintenance_due_id ? "Planification…" : "Planifier l'entretien"}
                      </button>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}
