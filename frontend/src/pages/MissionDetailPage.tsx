import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError, call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
import { ActionForm, Fact, Options } from "../components/forms";
import {
  formatDuration,
  formatTonnes,
  label,
  MISSION_EVENTS,
  MISSION_REASONS,
  MISSION_STATUS,
  MISSION_TONE,
  ROTATION_STATUS,
  WEIGHING_STATUS,
} from "../lib/labels";
import { useConnectivity } from "../lib/connectivity";
import { accountOf, queueWeighingTicket } from "../lib/hseOfflineSync";
import { listForAccount, type OutboxEntry } from "../lib/offline-outbox";
import { DEFERRABLE, pendingEventsOf, projectMission, queueMissionEvent, type ProgressEvent } from "../lib/offlineMissionEvents";
import { can } from "../lib/permissions";
import { formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";
import { OfflineIncidentQueue } from "./HseOffline";
import { WeighingForm } from "./WeighingPages";

type Mission = Schemas["MissionOut"];
type EventType = Schemas["MissionEventCreate"]["event_type"];
type Reason = NonNullable<Schemas["MissionEventCreate"]["reason_code"]>;

/** Étapes proposées selon l'état (docs/PLAN_LOT2.md §3) ; le serveur reste seul juge des transitions. */
function nextSteps(m: { status: string; rotations_completed: number }): EventType[] {
  switch (m.status) {
    case "ASSIGNED":
      return ["DEPARTED"];
    case "EN_ROUTE_EMPTY":
      return m.rotations_completed > 0 ? ["ARRIVED_LOADING", "COMPLETED"] : ["ARRIVED_LOADING"];
    case "LOADING":
      return ["LOADED"];
    case "EN_ROUTE_LOADED":
      return ["ARRIVED_UNLOADING"];
    case "UNLOADING":
      return ["UNLOADED", "COMPLETED"];
    case "SUSPENDED":
      return ["RESUMED"];
    default:
      return [];
  }
}

type Panel = "suspend" | "cancel" | "reassign" | null;

export function MissionDetailPage() {
  const { missionId = "" } = useParams();
  const me = useMe();
  const { timezoneOf } = useSites();
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  // Un même identifiant d'événement tant que l'envoi n'a pas abouti : un nouvel essai après coupure
  // réseau ou un double clic ne crée pas de doublon (RM-084).
  const attempt = useRef<{ event: string; id: string } | null>(null);
  const mission = useQuery({
    queryKey: ["mission", missionId],
    queryFn: () => call("get", "/missions/{mission_id}", { path: { mission_id: missionId } }),
  });
  const m = mission.data?.data;
  const etag = mission.data?.etag ?? null;
  const tz = timezoneOf(m?.site_id);
  const canProgress = m ? can(me.grants, "dispatch.mission.progress", m.site_id) : false;
  const canWeigh = m ? can(me.grants, "dispatch.weighing.record", m.site_id) : false;
  const [weighing, setWeighing] = useState<string | null>(null);
  // Pesées de la mission (lot 2b) : seulement pour les rôles qui les lisent.
  const tickets = useQuery({
    queryKey: ["weighing-tickets", "mission", missionId],
    enabled: Boolean(m) && can(me.grants, "dispatch.weighing.read", m?.site_id),
    queryFn: () => read("/weighing-tickets", { query: { mission_id: missionId, live_only: true, page_size: 200 } }),
  });
  const online = useConnectivity();
  const account = accountOf(me);
  const [outbox, setOutbox] = useState<OutboxEntry[]>([]);
  const [queuedCount, setQueuedCount] = useState(0);
  const reloadOutbox = useCallback(() => {
    listForAccount({ tenantId: account.tenantId, userId: account.userId }).then(setOutbox, () => setOutbox([]));
  }, [account.tenantId, account.userId]);
  useEffect(reloadOutbox, [reloadOutbox, queuedCount]);
  const waiting = pendingEventsOf(outbox, missionId);
  // Étapes proposées à partir de l'état projeté (événements en attente sur l'appareil compris).
  const projected = m
    ? projectMission(
        m.status,
        m.rotations_completed,
        waiting.map((e) => String(e.payload.event_type)),
      )
    : null;
  const liveTicket = new Map(
    (tickets.data?.items ?? []).filter((t) => t.status !== "VOIDED").map((t) => [t.rotation_id, t]),
  );

  async function queue(event: ProgressEvent, operationId: string) {
    if (!m) return;
    await queueMissionEvent(account, m, event, `${m.vehicle_fleet_number} — ${label(MISSION_EVENTS, event)}`, operationId);
    attempt.current = null;
    setQueuedCount((n) => n + 1);
  }

  async function send(event: EventType, extra: { reason_code?: Reason; vehicle_assignment_id?: string } = {}) {
    if (attempt.current?.event !== event) attempt.current = { event, id: crypto.randomUUID() };
    const operationId = attempt.current.id;
    setPending(true);
    setError(null);
    const deferrable = DEFERRABLE.has(event) && !extra.reason_code && !extra.vehicle_assignment_id;
    // Hors ligne, ou d'autres étapes déjà en attente sur l'appareil : l'ordre de saisie est conservé.
    if (deferrable && (!online || waiting.length > 0)) {
      try {
        await queue(event as ProgressEvent, operationId);
      } finally {
        setPending(false);
      }
      return;
    }
    try {
      await call("post", "/missions/{mission_id}/events", {
        path: { mission_id: missionId },
        ifMatch: etag,
        body: { event_type: event, client_event_id: operationId, deferred: false, ...extra },
      });
      attempt.current = null;
      setPanel(null);
      await queryClient.invalidateQueries({ queryKey: ["mission", missionId] });
      void queryClient.invalidateQueries({ queryKey: ["missions"] });
    } catch (err) {
      if (deferrable && err instanceof ApiError && err.status === 0) {
        // Réponse perdue ou coupure : même identifiant d'événement, rejoué depuis la file sans doublon.
        await queue(event as ProgressEvent, operationId);
        return;
      }
      setError(err);
      // Erreur métier (pas une coupure réseau) : l'essai suivant est une nouvelle demande.
      if ((err as { status?: number }).status !== 0) attempt.current = null;
      throw err;
    } finally {
      setPending(false);
    }
  }

  return (
    <section>
      <Link className="back" to="/missions">
        ← Missions
      </Link>
      <DataState loading={mission.isLoading} error={mission.error} empty={!m}>
        {m && (
          <>
            <div className="page-head">
              <h1>
                {m.origin_name} → {m.destination_name}{" "}
                <Badge tone={MISSION_TONE[m.status] ?? "neutral"}>{label(MISSION_STATUS, m.status)}</Badge>
              </h1>
            </div>
            {m.status === "SUSPENDED" && (
              <p className="warn-text">
                Suspendue ({label(MISSION_REASONS, m.status_reason)}) — reprise à l'étape «{" "}
                {label(MISSION_STATUS, m.status_before_suspension)} ».
              </p>
            )}
            {canProgress && (
              <div className="toolbar">
                {nextSteps({ status: projected?.status ?? m.status, rotations_completed: projected?.rotationsCompleted ?? m.rotations_completed }).map((step) => (
                  <button
                    key={step}
                    type="button"
                    className={step === "COMPLETED" ? undefined : "primary"}
                    disabled={pending}
                    onClick={() => void send(step).catch(() => undefined)}
                  >
                    {label(MISSION_EVENTS, step)}
                  </button>
                ))}
                {online && waiting.length === 0 && !["SUSPENDED", "COMPLETED", "CANCELLED"].includes(m.status) && (
                  <button type="button" disabled={pending} onClick={() => setPanel("suspend")}>
                    Suspendre
                  </button>
                )}
                {online && m.status === "SUSPENDED" && (
                  <button type="button" disabled={pending} onClick={() => setPanel("reassign")}>
                    Réaffecter à un autre véhicule
                  </button>
                )}
                {online && waiting.length === 0 && ["PLANNED", "ASSIGNED", "SUSPENDED"].includes(m.status) && (
                  <button type="button" disabled={pending} onClick={() => setPanel("cancel")}>
                    Annuler la mission
                  </button>
                )}
              </div>
            )}
            {error !== null && panel === null && <ErrorMessage error={error} />}
            {waiting.length > 0 && (
              <p className="warn-text small" role="status">
                {waiting.length} étape(s) saisie(s) sur l'appareil, en attente d'envoi
                {projected ? ` — état prévu : ${label(MISSION_STATUS, projected.status)}` : ""}. Elles seront appliquées si la
                mission n'a pas changé entre-temps ; suspension, réaffectation et annulation restent possibles en ligne
                une fois la file envoyée.
              </p>
            )}
            {canProgress && (
              <OfflineIncidentQueue
                account={account}
                canSync
                canOpen={false}
                timeZone={tz}
                refreshKey={queuedCount}
                onSynchronized={() => {
                  reloadOutbox();
                  void queryClient.invalidateQueries({ queryKey: ["mission", missionId] });
                }}
              />
            )}
            {panel === "suspend" && (
              <ReasonForm
                title="Suspendre la mission"
                submitLabel="Suspendre"
                onCancel={() => setPanel(null)}
                onSubmit={(reason) => send("SUSPENDED", { reason_code: reason })}
              />
            )}
            {panel === "cancel" && (
              <ReasonForm
                title="Annuler la mission (définitif)"
                submitLabel="Annuler la mission"
                danger
                onCancel={() => setPanel(null)}
                onSubmit={(reason) => send("CANCELLED", { reason_code: reason })}
              />
            )}
            {panel === "reassign" && (
              <Reassign
                mission={m}
                onCancel={() => setPanel(null)}
                onSubmit={(assignmentId) => send("REASSIGNED", { vehicle_assignment_id: assignmentId })}
              />
            )}
            <dl className="facts">
              <Fact label="Véhicule">{m.vehicle_fleet_number}</Fact>
              <Fact label="Conducteur">{m.driver_display_name}</Fact>
              <Fact label="Matière">{m.material_name}</Fact>
              {m.contract_reference && <Fact label="Contrat de transport">{m.contract_reference}</Fact>}
              <Fact label="Début prévu">{formatDateTime(m.planned_start, tz)}</Fact>
              <Fact label="Échéance">
                {m.due_at ? formatDateTime(m.due_at, tz) : null}
                {m.overdue && <span className="warn-text"> (dépassée)</span>}
              </Fact>
              <Fact label="Rotations">
                {m.rotations_completed}
                {m.planned_rotations ? ` sur ${m.planned_rotations} prévues` : ""}
              </Fact>
            </dl>
            <h2>Rotations</h2>
            <p className="muted small">
              Cycles chargement → déchargement déduits des étapes. Aucun tonnage ici : seules les pesées font foi.
            </p>
            <DataState loading={false} error={null} empty={(m.rotations ?? []).length === 0} emptyText="Aucune rotation.">
              <table>
                <thead>
                  <tr>
                    <th scope="col">N°</th>
                    <th scope="col">Début chargement</th>
                    <th scope="col">Fin de déchargement</th>
                    <th scope="col">Durée du cycle</th>
                    <th scope="col">Statut</th>
                    {tickets.isSuccess && <th scope="col">Pesée</th>}
                  </tr>
                </thead>
                <tbody>
                  {(m.rotations ?? []).map((r) => (
                    <tr key={r.rotation_id}>
                      <td>{r.sequence}</td>
                      <td>{formatDateTime(r.loading_started_at, tz)}</td>
                      <td>{formatDateTime(r.unloaded_at, tz)}</td>
                      <td>{formatDuration(r.cycle_seconds)}</td>
                      <td>{label(ROTATION_STATUS, r.status)}</td>
                      {tickets.isSuccess && (
                        <td>
                          {liveTicket.has(r.rotation_id) ? (
                            <>
                              {formatTonnes(liveTicket.get(r.rotation_id)?.net_kg)}{" "}
                              <span className="small muted">
                                ({label(WEIGHING_STATUS, liveTicket.get(r.rotation_id)?.status)})
                              </span>
                            </>
                          ) : canWeigh && r.status !== "ABORTED" && r.loaded_at ? (
                            <button type="button" onClick={() => setWeighing(r.rotation_id)}>
                              Saisir la pesée
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </DataState>
            {weighing && (
              <WeighingForm
                siteId={m.site_id}
                title="Nouvelle pesée"
                submitLabel="Enregistrer la pesée"
                onCancel={() => setWeighing(null)}
                onDone={() => {
                  setWeighing(null);
                  void queryClient.invalidateQueries({ queryKey: ["weighing-tickets"] });
                }}
                onSubmit={async (fields) => {
                  const body = { ...fields, rotation_id: weighing };
                  const summary = `${fields.ticket_number} — ${fields.gross_kg} kg`;
                  if (!online) {
                    // Pesée au pont bascule sans réseau : le ticket part dans la file du compte, tonnage
                    // toujours soumis à l'approbation à l'arrivée (ajout seul, RM-073).
                    await queueWeighingTicket(account, m.site_id, body, summary);
                    setWeighing(null);
                    setQueuedCount((n) => n + 1);
                    return;
                  }
                  // Clé d'idempotence dès l'envoi direct : si la réponse se perd, le ticket part dans la
                  // file avec la même clé et son rejeu renvoie la pesée déjà enregistrée (aucun doublon
                  // de tonnage) ; la dédup RM-074 reste le filet pour les renvois sans clé.
                  const operationId = crypto.randomUUID();
                  try {
                    await call("post", "/weighing-tickets", { body, idempotencyKey: operationId });
                  } catch (error) {
                    if (error instanceof ApiError && error.status === 0) {
                      await queueWeighingTicket(account, m.site_id, body, summary, new Date().toISOString(), operationId);
                      setWeighing(null);
                      setQueuedCount((n) => n + 1);
                      return;
                    }
                    throw error;
                  }
                }}
              />
            )}
            <h2>Chronologie</h2>
            <ol className="timeline">
              {(m.events ?? []).map((e) => (
                <li key={e.mission_event_id}>
                  <strong>{label(MISSION_EVENTS, e.event_type)}</strong> — {formatDateTime(e.occurred_at, tz)}
                  {e.reason && <span className="muted"> ({label(MISSION_REASONS, e.reason)})</span>}
                </li>
              ))}
            </ol>
          </>
        )}
      </DataState>
    </section>
  );
}

function ReasonForm({
  title,
  submitLabel,
  danger,
  onCancel,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  danger?: boolean;
  onCancel: () => void;
  onSubmit: (reason: Reason) => Promise<unknown>;
}) {
  const [reason, setReason] = useState<Reason>("BREAKDOWN");
  return (
    <ActionForm title={title} submitLabel={submitLabel} danger={danger} onCancel={onCancel} onSubmit={() => onSubmit(reason)}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value as Reason)}>
          <Options map={MISSION_REASONS} />
        </select>
      </label>
    </ActionForm>
  );
}

function Reassign({
  mission,
  onCancel,
  onSubmit,
}: {
  mission: Mission;
  onCancel: () => void;
  onSubmit: (assignmentId: string) => Promise<unknown>;
}) {
  const [choice, setChoice] = useState("");
  const candidates = useQuery({
    queryKey: ["assignments", "reassign", mission.site_id],
    queryFn: () =>
      read("/vehicle-assignments", { query: { site_id: mission.site_id, status: "ACTIVE", page_size: 200 } }),
  });
  return (
    <ActionForm title="Réaffecter la mission" submitLabel="Réaffecter" onCancel={onCancel} onSubmit={() => onSubmit(choice)}>
      <label>
        Nouvelle affectation (véhicule et conducteur du même site)
        <select required value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">— Choisir —</option>
          {(candidates.data?.items ?? [])
            .filter((a) => a.vehicle_id !== mission.vehicle_id)
            .map((a) => (
              <option key={a.vehicle_assignment_id} value={a.vehicle_assignment_id}>
                {a.vehicle_fleet_number} — {a.driver_display_name}
              </option>
            ))}
        </select>
      </label>
      <p className="muted small">Le cycle en cours est interrompu ; la mission repart de l'étape « Départ ».</p>
    </ActionForm>
  );
}
