/**
 * Avancement de mission saisi hors ligne (décisions du 18 novembre 2026).
 *
 * - Seuls les événements d'avancement sont différables ; suspension, réaffectation et annulation restent en ligne.
 * - Chaque événement garde son heure réelle et l'affectation connue à la saisie ; l'identifiant d'opération sert
 *   aussi de `client_event_id` : un rejeu (réponse perdue) ne crée jamais de doublon côté serveur.
 * - À la synchronisation, l'événement est appliqué s'il reste compatible avec l'état courant de la mission
 *   (le serveur revérifie la transition, l'ordre chronologique et l'affectation) ; sinon il est refusé et signalé.
 */
import type { Schemas } from "../api/client";
import { enqueue, MISSION_EVENT_ENDPOINT, type OutboxEntry } from "./offline-outbox";

type Mission = Schemas["MissionOut"];
export type ProgressEvent = "DEPARTED" | "ARRIVED_LOADING" | "LOADED" | "ARRIVED_UNLOADING" | "UNLOADED" | "COMPLETED";
export const DEFERRABLE: ReadonlySet<string> = new Set([
  "DEPARTED",
  "ARRIVED_LOADING",
  "LOADED",
  "ARRIVED_UNLOADING",
  "UNLOADED",
  "COMPLETED",
]);

const NEXT: Record<string, Record<string, string>> = {
  ASSIGNED: { DEPARTED: "EN_ROUTE_EMPTY" },
  EN_ROUTE_EMPTY: { ARRIVED_LOADING: "LOADING", COMPLETED: "COMPLETED" },
  LOADING: { LOADED: "EN_ROUTE_LOADED" },
  EN_ROUTE_LOADED: { ARRIVED_UNLOADING: "UNLOADING" },
  UNLOADING: { UNLOADED: "EN_ROUTE_EMPTY", COMPLETED: "COMPLETED" },
};

/** État projeté après les événements en attente (affichage seulement : le serveur reste seul juge). */
export function projectMission(
  status: string,
  rotationsCompleted: number,
  pending: readonly string[],
): { status: string; rotationsCompleted: number } {
  let current = status;
  let rotations = rotationsCompleted;
  for (const event of pending) {
    const target = NEXT[current]?.[event];
    if (!target) break; // incohérent localement : la projection s'arrête, le serveur tranchera
    if (event === "UNLOADED" || (event === "COMPLETED" && current === "UNLOADING")) rotations += 1;
    current = target;
  }
  return { status: current, rotationsCompleted: rotations };
}

/** Événements de cette mission encore en attente sur l'appareil, dans l'ordre de saisie. */
export function pendingEventsOf(entries: readonly OutboxEntry[], missionId: string): OutboxEntry[] {
  return entries.filter(
    (e) =>
      e.endpoint === MISSION_EVENT_ENDPOINT &&
      e.payload.mission_id === missionId &&
      (e.status === "pending" || e.status === "syncing"),
  );
}

export async function queueMissionEvent(
  account: { tenantId: string; userId: string },
  mission: Pick<Mission, "mission_id" | "site_id" | "vehicle_assignment_id">,
  event: ProgressEvent,
  summary: string,
  operationId: string = crypto.randomUUID(),
  occurredAt: string = new Date().toISOString(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId: mission.site_id,
    endpoint: MISSION_EVENT_ENDPOINT,
    payload: {
      mission_id: mission.mission_id,
      event_type: event,
      occurred_at: occurredAt,
      client_event_id: operationId,
      deferred: true,
      expected_vehicle_assignment_id: mission.vehicle_assignment_id,
    },
    createdAt: occurredAt,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}
