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
  pending?: {
    idempotencyKey: string;
    ifMatch: string;
    body: { action: "NOTE"; diagnosis: string; work_done: string; parts_note: string };
  };
}

const DB_NAME = "minefleet-offline-drafts-v1";
const STORE = "drafts";
const MAX_DRAFTS = 100;
const MAX_NOTE_LENGTH = 1000;

export function validateOfflineDraft(value: OfflineDraft): void {
  if (!/^[0-9a-f-]{36}$/i.test(value.id) || !/^[0-9a-f-]{36}$/i.test(value.workOrderId)) {
    throw new Error("Identifiant de brouillon invalide");
  }
  if (!/^[a-zA-Z0-9_-]{1,64}:[0-9a-f-]{36}$/i.test(value.ownerScope)) {
    throw new Error("Périmètre utilisateur/tenant invalide");
  }
  if (value.kind !== "work_order_note" || !value.note.trim() || value.note.length > MAX_NOTE_LENGTH) {
    throw new Error("Brouillon hors périmètre ou trop long");
  }
  if (!Number.isFinite(Date.parse(value.createdAt))) throw new Error("Date invalide");
  if (Object.keys(value).some((key) => !["id", "ownerScope", "kind", "workOrderId", "note", "createdAt", "pending"].includes(key))) {
    throw new Error("Champ non autorisé dans le stockage local");
  }
  if (value.pending !== undefined) {
    const p = value.pending;
    if (p === null || typeof p !== "object"
      || Object.keys(p).some((key) => !["idempotencyKey", "ifMatch", "body"].includes(key))
      || p.idempotencyKey !== value.id || !/^"[0-9]+"$/.test(p.ifMatch)
      || !p.body || typeof p.body !== "object"
      || Object.keys(p.body).some((key) => !["action", "diagnosis", "work_done", "parts_note"].includes(key))
      || p.body.action !== "NOTE" || p.body.work_done !== value.note.trim()
      || typeof p.body.diagnosis !== "string" || p.body.diagnosis.length > 4000
      || typeof p.body.parts_note !== "string" || p.body.parts_note.length > 2000) {
      throw new Error("Opération locale de transmission invalide");
    }
  }
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

/** Efface atomiquement les brouillons du seul compte et espace de travail actifs.
 * Une erreur annule l'ensemble de la transaction IndexedDB.
 */
export async function clearOfflineDrafts(ownerScope: string): Promise<void> {
  if (!/^[a-zA-Z0-9_-]{1,64}:[0-9a-f-]{36}$/i.test(ownerScope)) {
    throw new Error("Périmètre utilisateur/tenant invalide");
  }
  return transact<void>("readwrite", (store, set, reject) => {
    const cursor = store.index("ownerScope").openKeyCursor(IDBKeyRange.only(ownerScope));
    cursor.onsuccess = () => {
      const entry = cursor.result;
      if (!entry) { set(undefined); return; }
      const remove = store.delete(entry.primaryKey);
      remove.onsuccess = () => entry.continue();
      remove.onerror = () => reject(remove.error ?? new Error("Suppression impossible"));
    };
    cursor.onerror = () => reject(cursor.error ?? new Error("Parcours des brouillons impossible"));
  });
}

/** Prepare once: preserve the exact request across reconnects and ambiguous replies.
 * Do not call this helper for a fresh payload after the first transmission attempt.
 */
export async function prepareOfflineNoteTransmission(
  id: string,
  ownerScope: string,
  ifMatch: string,
  diagnosis: string,
  partsNote: string,
): Promise<NonNullable<OfflineDraft["pending"]>> {
  return transact<NonNullable<OfflineDraft["pending"]>>("readwrite", (store, set, reject) => {
    const req = store.get(id);
    req.onsuccess = () => {
      const draft = req.result as OfflineDraft | undefined;
      if (!draft || draft.ownerScope !== ownerScope || draft.kind !== "work_order_note") {
        reject(new Error("Brouillon inaccessible")); return;
      }
      if (draft.pending) {
        try { validateOfflineDraft(draft); set(draft.pending); } catch (error) {
          reject(error instanceof Error ? error : new Error("Brouillon invalide"));
        }
        return;
      }
      const pending: NonNullable<OfflineDraft["pending"]> = {
        idempotencyKey: draft.id,
        ifMatch,
        body: { action: "NOTE", diagnosis, work_done: draft.note.trim(), parts_note: partsNote },
      };
      const prepared = { ...draft, pending };
      try { validateOfflineDraft(prepared); } catch (error) {
        reject(error instanceof Error ? error : new Error("Brouillon invalide")); return;
      }
      const write = store.put(prepared);
      write.onsuccess = () => set(pending);
      write.onerror = () => reject(write.error ?? new Error("Préparation locale impossible"));
    };
    req.onerror = () => reject(req.error ?? new Error("Brouillon inaccessible"));
  });
}
