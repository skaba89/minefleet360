/**
 * Déclaration d'incident HSE hors ligne (premier parcours outbox de bout en bout).
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
  HSE_INCIDENT_ENDPOINT,
  listForAccount,
  updateEntry,
  type OutboxEntry,
} from "./offline-outbox";
import { withExclusiveOfflineSync, type LockManagerLike } from "./offline-sync-lock";
import { transitionAfterResponse } from "./offline-sync-state";

export type IncidentDraft = Schemas["IncidentCreate"];
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

export async function countUnsynchronized(account: Account): Promise<number> {
  return (await listForAccount(account)).filter((e) => e.status === "pending" || e.status === "syncing").length;
}

async function sendIncident(entry: OutboxEntry): Promise<{ id: string; reference: string }> {
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
  send: sendIncident,
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
      if (entry.endpoint !== HSE_INCIDENT_ENDPOINT || entry.tenantId !== account.tenantId || entry.userId !== account.userId) {
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
