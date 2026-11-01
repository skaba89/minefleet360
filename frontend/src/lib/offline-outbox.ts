/** File IndexedDB de commandes terrain, inactive tant qu'aucun parcours métier n'est autorisé. */
export type OutboxStatus = "pending" | "syncing" | "rejected";

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
}

const DB_NAME = "minefleet-field-outbox-v1";
const STORE = "operations";
const VERSION = 1;
/** Routes autorisées explicitement lors d'une future intégration métier. */
const ENABLED_ENDPOINTS: ReadonlySet<string> = new Set();

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
export async function listPending(tenantId: string, userId: string): Promise<OutboxEntry[]> {
  if (!tenantId || !userId) throw new Error("Compte requis");
  const entries = await runTransaction<OutboxEntry[]>("readonly", (store, resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result as OutboxEntry[]);
    request.onerror = () => reject(request.error ?? new Error("Lecture impossible"));
  });
  return entries
    .filter((e) => e.tenantId === tenantId && e.userId === userId && e.status === "pending")
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.operationId.localeCompare(b.operationId));
}

/** À appeler à la déconnexion selon la politique de purge de données locales. */
export async function purgeOutbox(): Promise<void> {
  await runTransaction<void>("readwrite", (store, resolve, reject) => {
    const request = store.clear();
    request.onsuccess = () => resolve(undefined);
    request.onerror = () => reject(request.error ?? new Error("Purge impossible"));
  });
}
