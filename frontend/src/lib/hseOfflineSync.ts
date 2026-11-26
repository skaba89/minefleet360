/**
 * Saisies terrain hors ligne (incidents et inspections HSE, relevés de compteur, signalements de panne) :
 * file outbox de bout en bout.
 *
 * - La saisie est enregistrée dans l'outbox IndexedDB, liée au tenant, au compte et au site.
 * - La synchronisation est déclenchée explicitement (retour du réseau, bouton, minuterie), sous verrou
 *   Web Locks exclusif par compte : deux onglets n'envoient jamais la même file en parallèle.
 * - Chaque envoi porte `Idempotency-Key = operationId` : le serveur crée l'incident une seule fois, revérifie
 *   l'authentification, le droit de déclarer et le site, et renvoie l'incident d'origine en cas de rejeu.
 * - Une opération n'est « synchronisée » qu'après une réponse 2xx portant la référence serveur.
 */
import { ApiError, request, type Schemas } from "../api/client";
import {
  enqueue,
  FUEL_ISSUE_ENDPOINT,
  HSE_INCIDENT_ENDPOINT,
  HSE_INSPECTION_ENDPOINT,
  isSyncableEndpoint,
  listForAccount,
  METER_READING_ENDPOINT,
  MISSION_EVENT_ENDPOINT,
  WEIGHING_TICKET_ENDPOINT,
  WORK_ORDER_ENDPOINT,
  updateEntry,
  type OutboxEntry,
} from "./offline-outbox";
import { label, MISSION_STATUS } from "./labels";
import { withExclusiveOfflineSync, type LockManagerLike } from "./offline-sync-lock";
import { transitionAfterResponse } from "./offline-sync-state";

export type IncidentDraft = Schemas["IncidentCreate"];
export type InspectionDraft = Schemas["InspectionCreate"];
export type Account = { tenantId: string; userId: string };

export interface SyncDeps {
  list: (account: Account) => Promise<OutboxEntry[]>;
  update: (entry: OutboxEntry) => Promise<void>;
  send: (entry: OutboxEntry) => Promise<{ id: string; reference: string }>;
  locks: LockManagerLike | null;
  now: () => number;
}

export type SyncResult =
  | { kind: "locked" }
  | { kind: "done"; synchronized: number; rejected: number; waiting: number }
  | { kind: "reauthenticate" };

export function accountOf(me: { workspace_code: string; user_account_id: string }): Account {
  return { tenantId: me.workspace_code, userId: me.user_account_id };
}

export async function queueIncident(
  account: Account,
  body: IncidentDraft,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId: body.site_id,
    endpoint: HSE_INCIDENT_ENDPOINT,
    payload: { ...body },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
  };
  await enqueue(entry);
  return entry;
}

/**
 * Inspection HSE saisie sans réseau (ou dont la réponse s'est perdue) : même file, même clé d'idempotence.
 * `summary` (nom de la checklist) sert seulement à l'affichage local ; il n'est jamais envoyé.
 */
export async function queueInspection(
  account: Account,
  body: InspectionDraft,
  summary: string,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId: body.site_id,
    endpoint: HSE_INSPECTION_ENDPOINT,
    payload: { ...body },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}

export type MeterReadingDraft = Schemas["MeterReadingCreate"] & { read_at: string };

/**
 * Relevé de compteur saisi sans réseau : l'engin voyage dans la charge utile locale et n'est jamais envoyé
 * dans le corps (il est dans l'URL). `read_at` est obligatoire : l'heure du relevé, pas celle de l'envoi.
 */
export async function queueMeterReading(
  account: Account,
  siteId: string,
  vehicleId: string,
  body: MeterReadingDraft,
  summary: string,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId,
    endpoint: METER_READING_ENDPOINT,
    payload: { vehicle_id: vehicleId, meter_kind: body.meter_kind, value: body.value, read_at: body.read_at },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}

export type BreakdownDraft = Schemas["WorkOrderCreate"] & { reported_at: string };

/**
 * Signalement de panne saisi sans réseau : `reported_at` porte l'heure du constat ; une panne bloquante
 * n'immobilise l'engin qu'à la synchronisation (l'écran le signale).
 */
export async function queueBreakdown(
  account: Account,
  siteId: string,
  body: BreakdownDraft,
  summary: string,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId,
    endpoint: WORK_ORDER_ENDPOINT,
    payload: { ...body },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}

export type FuelIssueDraft = Schemas["IssueCreate"];

/**
 * Sortie de carburant (demande de ravitaillement) saisie sans réseau : `requested_at` porte l'heure de la
 * demande. La sortie arrive PENDING_APPROVAL : l'approbation reste un contrôle séparé, jamais contourné.
 */
export async function queueFuelIssue(
  account: Account,
  siteId: string,
  body: FuelIssueDraft,
  summary: string,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId,
    endpoint: FUEL_ISSUE_ENDPOINT,
    payload: { ...body },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}

export type WeighingTicketDraft = Schemas["WeighingCreate"];

/**
 * Ticket de pesée saisi sans réseau au pont bascule : le numéro de ticket imprimé et l'heure de la pesée
 * voyagent dans la charge utile ; le tonnage reste soumis à l'approbation (ajout seul, RM-073) et la
 * dédup métier RM-074 (pont + numéro) reste intacte pour les renvois sans clé.
 */
export async function queueWeighingTicket(
  account: Account,
  siteId: string,
  body: WeighingTicketDraft,
  summary: string,
  nowIso = new Date().toISOString(),
  operationId: string = crypto.randomUUID(),
): Promise<OutboxEntry> {
  const entry: OutboxEntry = {
    operationId,
    tenantId: account.tenantId,
    userId: account.userId,
    siteId,
    endpoint: WEIGHING_TICKET_ENDPOINT,
    payload: { ...body },
    createdAt: nowIso,
    status: "pending",
    attempts: 0,
    summary: summary.slice(0, 200),
  };
  await enqueue(entry);
  return entry;
}

export async function countUnsynchronized(account: Account): Promise<number> {
  return (await listForAccount(account)).filter((e) => e.status === "pending" || e.status === "syncing").length;
}

async function sendEntry(entry: OutboxEntry): Promise<{ id: string; reference: string }> {
  if (entry.endpoint === MISSION_EVENT_ENDPOINT) {
    const { mission_id: missionId, ...body } = entry.payload;
    if (typeof missionId !== "string" || !/^[0-9a-f-]{36}$/i.test(missionId)) throw new Error("Mission invalide");
    const path = `/missions/${missionId}`;
    // Version courante relue à l'envoi : l'événement est appliqué s'il reste compatible avec l'état
    // (transition, ordre chronologique, affectation attendue revérifiés par le serveur), jamais forcé.
    const current = await request<Schemas["MissionOut"]>(path, { method: "GET" });
    const { data } = await request<Schemas["MissionOut"]>(`${path}/events`, {
      method: "POST",
      body,
      ifMatch: current.etag,
    });
    if (!data?.mission_id) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.mission_id, reference: label(MISSION_STATUS, data.status) };
  }
  if (entry.endpoint === WORK_ORDER_ENDPOINT) {
    const { data } = await request<Schemas["WorkOrderOut"]>(entry.endpoint, {
      method: "POST",
      body: entry.payload,
      idempotencyKey: entry.operationId,
    });
    if (!data?.work_order_id || !data.reference) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.work_order_id, reference: data.reference };
  }
  if (entry.endpoint === METER_READING_ENDPOINT) {
    const { vehicle_id: vehicleId, ...body } = entry.payload;
    if (typeof vehicleId !== "string" || !/^[0-9a-f-]{36}$/i.test(vehicleId)) throw new Error("Engin invalide");
    const { data } = await request<Schemas["MeterReadingOut"]>(`/vehicles/${vehicleId}/meter-readings`, {
      method: "POST",
      body,
      idempotencyKey: entry.operationId,
    });
    if (!data?.vehicle_meter_reading_id) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.vehicle_meter_reading_id, reference: `relevé ${data.value}` };
  }
  if (entry.endpoint === HSE_INSPECTION_ENDPOINT) {
    const { data } = await request<Schemas["InspectionOut"]>(entry.endpoint, {
      method: "POST",
      body: entry.payload,
      idempotencyKey: entry.operationId,
    });
    if (!data?.hse_inspection_id || !data.reference) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.hse_inspection_id, reference: data.reference };
  }
  if (entry.endpoint === FUEL_ISSUE_ENDPOINT) {
    const { data } = await request<Schemas["FuelIssueOut"]>(entry.endpoint, {
      method: "POST",
      body: entry.payload,
      idempotencyKey: entry.operationId,
    });
    if (!data?.fuel_issue_id) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.fuel_issue_id, reference: `sortie ${data.liters} L — ${data.tank_code}` };
  }
  if (entry.endpoint === WEIGHING_TICKET_ENDPOINT) {
    const { data } = await request<Schemas["WeighingOut"]>(entry.endpoint, {
      method: "POST",
      body: entry.payload,
      idempotencyKey: entry.operationId,
    });
    if (!data?.weighing_ticket_id || !data?.ticket_number) throw new Error("Accusé de réception serveur incomplet");
    return { id: data.weighing_ticket_id, reference: data.ticket_number };
  }
  if (entry.endpoint !== HSE_INCIDENT_ENDPOINT) throw new Error("Opération hors ligne non prise en charge");
  const { data } = await request<Schemas["IncidentOut"]>(entry.endpoint, {
    method: "POST",
    body: entry.payload,
    idempotencyKey: entry.operationId,
  });
  if (!data?.hse_incident_id || !data.reference) throw new Error("Accusé de réception serveur incomplet");
  return { id: data.hse_incident_id, reference: data.reference };
}

function browserLocks(): LockManagerLike | null {
  const locks = typeof navigator !== "undefined" ? (navigator as { locks?: unknown }).locks : undefined;
  return (locks as LockManagerLike | undefined) ?? null;
}

export const defaultSyncDeps: SyncDeps = {
  list: listForAccount,
  update: updateEntry,
  send: sendEntry,
  locks: browserLocks(),
  now: () => Date.now(),
};

/** Statut HTTP d'un échec : null pour une coupure réseau ou une réponse inexploitable (rejouable). */
function statusOf(error: unknown): number | null {
  if (error instanceof ApiError) return error.status === 0 ? null : error.status;
  return null;
}

/**
 * Synchronise la file du compte, dans l'ordre de saisie. Une erreur transitoire arrête la passe (l'ordre
 * est préservé) ; un rejet définitif est marqué et la passe continue ; un 401 interrompt tout.
 */
export async function syncAccount(account: Account, deps: SyncDeps = defaultSyncDeps): Promise<SyncResult> {
  const lockScope = { tenantId: account.tenantId, userId: account.userId, siteId: "*" };
  const locked = await withExclusiveOfflineSync(lockScope, deps.locks, async (): Promise<SyncResult> => {
    let synchronized = 0;
    let rejected = 0;
    // Relue sous verrou : un autre onglet a pu terminer des opérations entre-temps.
    const queue = (await deps.list(account)).filter((e) => e.status === "pending" || e.status === "syncing");
    for (let index = 0; index < queue.length; index += 1) {
      const entry = queue[index]!;
      if (!isSyncableEndpoint(entry.endpoint) || entry.tenantId !== account.tenantId || entry.userId !== account.userId) {
        continue;
      }
      // Une opération « syncing » orpheline (onglet fermé en plein envoi) est rejouable : la clé est stable.
      if (entry.status === "pending" && entry.retryAt && entry.retryAt > deps.now()) {
        return { kind: "done", synchronized, rejected, waiting: queue.length - index };
      }
      await deps.update({ ...entry, status: "syncing" });
      try {
        const ack = await deps.send(entry);
        await deps.update({
          ...entry,
          status: "synchronized",
          attempts: entry.attempts + 1,
          retryAt: null,
          errorCode: undefined,
          serverId: ack.id,
          serverReference: ack.reference,
          syncedAt: new Date(deps.now()).toISOString(),
        });
        synchronized += 1;
      } catch (error) {
        const outcome = transitionAfterResponse(entry.attempts, statusOf(error), deps.now());
        if (outcome.state === "rejected") {
          const code = error instanceof ApiError ? error.code : outcome.errorCode ?? "REJECTED";
          await deps.update({ ...entry, status: "rejected", attempts: outcome.attempts, retryAt: null, errorCode: code });
          rejected += 1;
          continue;
        }
        if (outcome.state === "reauthenticate") {
          await deps.update({ ...entry, status: "pending", attempts: outcome.attempts, retryAt: null, errorCode: "SESSION_EXPIRED" });
          return { kind: "reauthenticate" };
        }
        await deps.update({
          ...entry,
          status: "pending",
          attempts: outcome.attempts,
          retryAt: outcome.retryAt,
          errorCode: error instanceof ApiError ? error.code : "NETWORK_ERROR",
        });
        return { kind: "done", synchronized, rejected, waiting: queue.length - index };
      }
    }
    return { kind: "done", synchronized, rejected, waiting: 0 };
  });
  return locked.acquired ? locked.result : { kind: "locked" };
}
