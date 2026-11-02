/** File IndexedDB de commandes terrain : seules les routes explicitement activées sont acceptées. */
import { assertOfflinePayloadSafe } from "./offline-payload-guard";
import { identityKey, type OfflineIdentity } from "./offline-scope";

export type OutboxStatus = "pending" | "syncing" | "synchronized" | "rejected";

export interface OutboxEntry {
  operationId: string;
  tenantId: string;
  userId: string;
  siteId: string;
  endpoint: string;
  payload: Record<string, unknown>;
  createdAt: string;
  status: OutboxStatus;
  attempts: number;
  errorCode?: string;
  /** Prochaine tentative autorisée (ms epoch) après une erreur transitoire. */
  retryAt?: number | null;
  /** Accusé de réception serveur : présent seulement après une réponse 2xx. */
  serverId?: string;
  serverReference?: string;
  syncedAt?: string;
}

/** Durée maximale de conservation locale d'une opération non synchronisée. */
export const OUTBOX_RETENTION_MS = 7 * 24 * 3600 * 1000;

const DB_NAME = "minefleet-field-outbox-v1";
const STORE = "operations";
const VERSION = 1;
/** Routes autorisées explicitement : déclarations append-only et idempotentes côté serveur. */
export const HSE_INCIDENT_ENDPOINT = "/hse/incidents";
const ENABLED_ENDPOINTS: ReadonlySet<string> = new Set([HSE_INCIDENT_ENDPOINT]);

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB indisponible"));
      return;
    }
    const request = indexedDB.open(DB_NAME, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "operationId" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Ouverture IndexedDB impossible"));
  });
}

function runTransaction<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore, resolve: (value: T) => void, reject: (error: Error) => void) => void,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        let value: T;
        let ready = false;
        tx.oncomplete = () => {
          db.close();
          if (ready) resolve(value);
          else reject(new Error("Résultat IndexedDB indisponible"));
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error ?? new Error("Transaction IndexedDB échouée"));
        };
        tx.onabort = () => {
          db.close();
          reject(tx.error ?? new Error("Transaction IndexedDB annulée"));
        };
        operation(store, (result) => {
          value = result;
          ready = true;
        }, reject);
      }),
  );
}

export function assertAllowedEntry(entry: OutboxEntry): void {
  if (!ENABLED_ENDPOINTS.has(entry.endpoint)) {
    throw new Error("Synchronisation hors ligne indisponible pour cette opération");
  }
  assertOfflinePayloadSafe(entry.payload);
  if (
    !entry.operationId ||
    !entry.tenantId ||
    !entry.userId ||
    !entry.siteId ||
    entry.status !== "pending" ||
    entry.attempts !== 0 ||
    !Number.isFinite(Date.parse(entry.createdAt))
  ) {
    throw new Error("Opération hors ligne invalide");
  }
}

/** Refuse toute écriture métier jusqu'à validation et activation d'une route spécifique. */
export async function enqueue(entry: OutboxEntry): Promise<void> {
  assertAllowedEntry(entry);
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const request = store.add(entry);
    request.onsuccess = () => resolve(undefined);
    request.onerror = () => reject(request.error ?? new Error("Enregistrement impossible"));
  });
}

/** Le périmètre est toujours imposé par le compte courant, jamais depuis l'entrée stockée. */
export async function listPending(identity: OfflineIdentity): Promise<OutboxEntry[]> {
  const currentScope = identityKey(identity);
  return (await readAll())
    .filter((e) => identityKey(e) === currentScope && e.status === "pending")
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.operationId.localeCompare(b.operationId));
}

function readAll(): Promise<OutboxEntry[]> {
  return runTransaction<OutboxEntry[]>("readonly", (store, resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result as OutboxEntry[]);
    request.onerror = () => reject(request.error ?? new Error("Lecture impossible"));
  });
}

function sameAccount(entry: OutboxEntry, account: { tenantId: string; userId: string }): boolean {
  if (!account.tenantId || !account.userId) throw new Error("Identité terrain incomplète");
  return entry.tenantId === account.tenantId && entry.userId === account.userId;
}

/** Toutes les opérations d'un compte (tous sites, tous états), dans l'ordre de saisie. */
export async function listForAccount(account: { tenantId: string; userId: string }): Promise<OutboxEntry[]> {
  return (await readAll())
    .filter((e) => sameAccount(e, account))
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.operationId.localeCompare(b.operationId));
}

/** Remplace une opération existante du même compte ; l'identité et la charge sont immuables. */
export async function updateEntry(entry: OutboxEntry): Promise<void> {
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const get = store.get(entry.operationId);
    get.onsuccess = () => {
      const current = get.result as OutboxEntry | undefined;
      if (
        !current ||
        current.tenantId !== entry.tenantId ||
        current.userId !== entry.userId ||
        current.siteId !== entry.siteId ||
        current.endpoint !== entry.endpoint ||
        JSON.stringify(current.payload) !== JSON.stringify(entry.payload)
      ) {
        reject(new Error("Opération hors ligne introuvable ou altérée"));
        return;
      }
      const put = store.put(entry);
      put.onsuccess = () => resolve(undefined);
      put.onerror = () => reject(put.error ?? new Error("Mise à jour impossible"));
    };
    get.onerror = () => reject(get.error ?? new Error("Lecture impossible"));
  });
}

/** Retire une opération terminée (synchronisée ou rejetée) à la demande de son auteur. */
export async function removeEntry(account: { tenantId: string; userId: string }, operationId: string): Promise<void> {
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const get = store.get(operationId);
    get.onsuccess = () => {
      const current = get.result as OutboxEntry | undefined;
      if (!current || !sameAccount(current, account)) {
        resolve(undefined);
        return;
      }
      if (current.status === "pending" || current.status === "syncing") {
        reject(new Error("Une opération non synchronisée ne peut pas être retirée"));
        return;
      }
      const del = store.delete(operationId);
      del.onsuccess = () => resolve(undefined);
      del.onerror = () => reject(del.error ?? new Error("Suppression impossible"));
    };
    get.onerror = () => reject(get.error ?? new Error("Lecture impossible"));
  });
}

/**
 * Expiration de session : seules les opérations en attente du compte qui expire sont conservées, pour être
 * rejouées après sa reconnexion (jamais sous un autre compte). Tout le reste, et tout ce qui dépasse la
 * durée de rétention, est supprimé.
 */
export async function purgeOutboxKeepingPending(
  account: { tenantId: string; userId: string },
  nowMs: number = Date.now(),
): Promise<void> {
  if (!account.tenantId || !account.userId) throw new Error("Identité terrain incomplète");
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const request = store.openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) {
        resolve(undefined);
        return;
      }
      const entry = cursor.value as OutboxEntry;
      const keep =
        sameAccount(entry, account) &&
        (entry.status === "pending" || entry.status === "syncing") &&
        nowMs - Date.parse(entry.createdAt) < OUTBOX_RETENTION_MS;
      if (!keep) cursor.delete();
      cursor.continue();
    };
    request.onerror = () => reject(request.error ?? new Error("Purge impossible"));
  });
}

/** Déconnexion volontaire : toute la file locale est supprimée (appareil potentiellement partagé). */
export async function purgeOutbox(): Promise<void> {
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const request = store.clear();
    request.onsuccess = () => resolve(undefined);
    request.onerror = () => reject(request.error ?? new Error("Purge impossible"));
  });
}
