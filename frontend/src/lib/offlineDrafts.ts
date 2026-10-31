/** File locale de brouillons de synchronisation, volontairement sans rejeu automatique.
 * Les données restent sur cet appareil : ne pas y placer GPS, secrets ou données personnelles.
 */
export interface OfflineDraft {
  id: string;
  ownerScope: string;
  kind: "work_order_note";
  workOrderId: string;
  note: string;
  createdAt: string;
}

const DB_NAME = "minefleet-offline-drafts-v1";
const STORE = "drafts";
const MAX_DRAFTS = 100;
const MAX_NOTE_LENGTH = 1000;

export function validateOfflineDraft(value: OfflineDraft): void {
  if (!/^[0-9a-f-]{36}$/i.test(value.id) || !/^[0-9a-f-]{36}$/i.test(value.workOrderId)) {
    throw new Error("Identifiant de brouillon invalide");
  }
  if (!/^[0-9a-f-]{36}:[0-9a-f-]{36}$/i.test(value.ownerScope)) {
    throw new Error("Périmètre utilisateur/tenant invalide");
  }
  if (value.kind !== "work_order_note" || !value.note.trim() || value.note.length > MAX_NOTE_LENGTH) {
    throw new Error("Brouillon hors périmètre ou trop long");
  }
  if (!Number.isFinite(Date.parse(value.createdAt))) throw new Error("Date invalide");
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB indisponible"));
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("ownerScope", "ownerScope", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("Ouverture IndexedDB impossible"));
    req.onblocked = () => reject(new Error("IndexedDB verrouillée par un autre onglet"));
  });
}

async function transact<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore, resolve: (value: T) => void, reject: (error: Error) => void) => void,
): Promise<T> {
  const db = await openDatabase();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    let settled = false;
    let value: T;
    const fail = (error: Error) => { if (!settled) { settled = true; reject(error); } };
    const store = tx.objectStore(STORE);
    action(store, (result) => { value = result; }, fail);
    tx.oncomplete = () => { db.close(); if (!settled) { settled = true; resolve(value); } };
    tx.onerror = () => { db.close(); fail(tx.error ?? new Error("Transaction IndexedDB échouée")); };
    tx.onabort = () => { db.close(); fail(tx.error ?? new Error("Transaction IndexedDB annulée")); };
  });
}

export async function listOfflineDrafts(ownerScope: string): Promise<OfflineDraft[]> {
  return transact<OfflineDraft[]>("readonly", (store, set, reject) => {
    const req = store.index("ownerScope").getAll(IDBKeyRange.only(ownerScope));
    req.onsuccess = () => set((req.result as OfflineDraft[]).sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
    req.onerror = () => reject(req.error ?? new Error("Lecture impossible"));
  });
}

export async function saveOfflineDraft(draft: OfflineDraft): Promise<void> {
  validateOfflineDraft(draft);
  return transact<void>("readwrite", (store, set, reject) => {
    const idx = store.index("ownerScope");
    const count = idx.count(IDBKeyRange.only(draft.ownerScope));
    count.onsuccess = () => {
      if (count.result >= MAX_DRAFTS) { reject(new Error("Limite de brouillons atteinte")); return; }
      const req = store.add(draft);
      req.onsuccess = () => set(undefined);
      req.onerror = () => reject(req.error ?? new Error("Enregistrement impossible"));
    };
    count.onerror = () => reject(count.error ?? new Error("Comptage impossible"));
  });
}

export async function discardOfflineDraft(id: string, ownerScope: string): Promise<void> {
  return transact<void>("readwrite", (store, set, reject) => {
    const found = store.get(id);
    found.onsuccess = () => {
      if (!found.result || (found.result as OfflineDraft).ownerScope !== ownerScope) {
        reject(new Error("Brouillon inaccessible"));
        return;
      }
      const remove = store.delete(id);
      remove.onsuccess = () => set(undefined);
      remove.onerror = () => reject(remove.error ?? new Error("Suppression impossible"));
    };
    found.onerror = () => reject(found.error ?? new Error("Lecture impossible"));
  });
}

/** À déclencher lors de la déconnexion après confirmation explicite de la perte des brouillons locaux. */
export async function clearOfflineDrafts(ownerScope: string): Promise<void> {
  const drafts = await listOfflineDrafts(ownerScope);
  await Promise.all(drafts.map((draft) => discardOfflineDraft(draft.id, ownerScope)));
}
