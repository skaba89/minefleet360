import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime, zonedInputToUtc } from "../lib/time";

type PlanStatus = Schemas["PreventivePlanStatusOut"];
type Declaration = Schemas["ServiceDeclarationOut"];

const STATUS_LABEL: Record<PlanStatus["status"], string> = {
  DUE: "Entretien dû",
  UPCOMING: "À venir",
  INSUFFICIENT_DATA: "Information insuffisante",
  NOT_CONFIGURED: "Non configuré",
};
const SOURCE_LABEL: Record<PlanStatus["baseline_source"], string> = {
  WORK_ORDER: "Dernier OT préventif clôturé",
  DECLARATION: "Dernier entretien déclaré",
  INITIAL_REQUIRED: "Dernier entretien inconnu : entretien initial",
  NONE: "Aucun point de départ",
};
const DECISION_LABEL: Record<Declaration["status"], string> = {
  PENDING: "En attente de validation",
  APPROVED: "Approuvée",
  REJECTED: "Rejetée",
};

function meter(value: string | number | null | undefined, reliable: boolean, remaining: string | number | null | undefined) {
  if (!reliable) return "Compteur non fiable (baisse constatée) : nouvelle déclaration requise";
  if (value == null) return "—";
  return remaining == null ? String(value) : `${String(value)} (reste ${String(remaining)})`;
}

/** État calculé de chaque plan et déclaration du dernier entretien connu (point de départ), validée par un tiers. */
export function VehiclePreventiveStatus({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const allowed = can(me.grants, "maintenance.preventive.read", siteId);
  const managing = can(me.grants, "maintenance.preventive.manage", siteId);
  const [planCode, setPlanCode] = useState<string | null>(null);
  const [knowledge, setKnowledge] = useState<"KNOWN" | "UNKNOWN">("KNOWN");
  const [servicedAt, setServicedAt] = useState("");
  const [km, setKm] = useState("");
  const [hours, setHours] = useState("");
  const [note, setNote] = useState("");
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const statuses = useQuery({
    queryKey: ["preventive-status", vehicleId],
    queryFn: () => get<PlanStatus[]>(`/vehicles/${vehicleId}/preventive-status`),
    enabled: allowed,
  });
  const declarations = useQuery({
    queryKey: ["preventive-declarations", vehicleId],
    queryFn: () => get<Declaration[]>(`/vehicles/${vehicleId}/preventive-declarations`),
    enabled: allowed,
  });

  if (!allowed) return null;

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["preventive-status", vehicleId] });
    await queryClient.invalidateQueries({ queryKey: ["preventive-declarations", vehicleId] });
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
      return true;
    } catch (failure) {
      setError(failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function declare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!planCode) return;
    const known = knowledge === "KNOWN";
    const ok = await run(() =>
      request("/preventive-declarations", {
        method: "POST",
        body: {
          vehicle_id: vehicleId,
          plan_code: planCode,
          knowledge,
          serviced_at: known && servicedAt ? zonedInputToUtc(servicedAt, me.timezone).toISOString() : null,
          odometer_km: known && km ? km : null,
          hour_meter: known && hours ? hours : null,
          note: note.trim() || null,
        },
      }),
    );
    if (ok) {
      setPlanCode(null);
      setServicedAt("");
      setKm("");
      setHours("");
      setNote("");
    }
  }

  function decide(id: string, decision: "APPROVE" | "REJECT", decisionNote?: string) {
    void run(() =>
      request(`/preventive-declarations/${id}/decide`, { method: "POST", body: { decision, note: decisionNote ?? null } }),
    ).then((ok) => {
      if (ok) {
        setRejectingId(null);
        setReason("");
      }
    });
  }

  const pending = (declarations.data ?? []).filter((d) => d.status === "PENDING");

  return (
    <section aria-label="État des plans préventifs">
      <h2>État des plans et dernier entretien</h2>
      {error != null ? <ErrorMessage error={error} /> : null}
      <DataState loading={statuses.isLoading} error={statuses.error} empty={!statuses.data?.length} emptyText="Aucun plan actif.">
        <table>
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">État</th>
              <th scope="col">Point de départ</th>
              <th scope="col">Km</th>
              <th scope="col">Heures</th>
              <th scope="col">Date d'échéance</th>
              {managing && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {(statuses.data ?? []).map((plan) => (
              <tr key={plan.maintenance_plan_id}>
                <td>{plan.code}</td>
                <td>{STATUS_LABEL[plan.status]}</td>
                <td>
                  {SOURCE_LABEL[plan.baseline_source]}
                  {plan.serviced_on ? ` (${formatDate(plan.serviced_on)})` : ""}
                </td>
                <td>{meter(plan.current_km, plan.km_reliable, plan.remaining_km)}</td>
                <td>{meter(plan.current_hours, plan.hours_reliable, plan.remaining_hours)}</td>
                <td>{plan.due_on ? formatDate(plan.due_on) : "—"}</td>
                {managing && (
                  <td>
                    <button type="button" disabled={busy} onClick={() => setPlanCode(plan.code)}>
                      Déclarer le dernier entretien
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>

      {managing && planCode && (
        <form onSubmit={(event) => void declare(event)} aria-label="Déclarer le dernier entretien">
          <h3>Dernier entretien connu — plan {planCode}</h3>
          <p className="muted small">Une autre personne devra valider cette déclaration avant qu'elle serve de point de départ.</p>
          <label>
            <input type="radio" name="knowledge" checked={knowledge === "KNOWN"} onChange={() => setKnowledge("KNOWN")} />
            Connu
          </label>
          <label>
            <input type="radio" name="knowledge" checked={knowledge === "UNKNOWN"} onChange={() => setKnowledge("UNKNOWN")} />
            Inconnu (un entretien initial sera demandé)
          </label>
          {knowledge === "KNOWN" && (
            <>
              <label>
                Date et heure du dernier entretien ({me.timezone})
                <input type="datetime-local" required value={servicedAt} onChange={(e) => setServicedAt(e.target.value)} />
              </label>
              <label>
                Kilométrage ce jour-là
                <input type="number" min="0" step="0.1" value={km} onChange={(e) => setKm(e.target.value)} />
              </label>
              <label>
                Heures moteur ce jour-là
                <input type="number" min="0" step="0.1" value={hours} onChange={(e) => setHours(e.target.value)} />
              </label>
            </>
          )}
          <label>
            Justificatif ou remarque
            <input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>Envoyer pour validation</button>
          <button type="button" disabled={busy} onClick={() => setPlanCode(null)}>Annuler</button>
        </form>
      )}

      <h3>Déclarations du dernier entretien</h3>
      <DataState loading={declarations.isLoading} error={declarations.error} empty={!declarations.data?.length} emptyText="Aucune déclaration.">
        <table>
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Dernier entretien</th>
              <th scope="col">Km</th>
              <th scope="col">Heures</th>
              <th scope="col">Décision</th>
              {managing && pending.length > 0 && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {(declarations.data ?? []).map((d) => (
              <tr key={d.service_declaration_id}>
                <td>{d.plan_code}</td>
                <td>{d.knowledge === "UNKNOWN" ? "Inconnu" : formatDateTime(d.serviced_at, me.timezone)}</td>
                <td>{d.odometer_km ?? "—"}</td>
                <td>{d.hour_meter ?? "—"}</td>
                <td>
                  {DECISION_LABEL[d.status]}
                  {d.decision_note ? ` — ${d.decision_note}` : ""}
                </td>
                {managing && pending.length > 0 && (
                  <td>
                    {d.status === "PENDING" &&
                      (d.declared_by === me.user_account_id ? (
                        <span className="muted small">À valider par une autre personne</span>
                      ) : rejectingId === d.service_declaration_id ? (
                        <span>
                          <input aria-label="Motif du rejet" maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
                          <button type="button" disabled={busy || !reason.trim()} onClick={() => decide(d.service_declaration_id, "REJECT", reason.trim())}>
                            Confirmer le rejet
                          </button>
                        </span>
                      ) : (
                        <span>
                          <button type="button" disabled={busy} onClick={() => decide(d.service_declaration_id, "APPROVE")}>
                            Approuver
                          </button>
                          <button type="button" disabled={busy} onClick={() => setRejectingId(d.service_declaration_id)}>
                            Rejeter
                          </button>
                        </span>
                      ))}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}
