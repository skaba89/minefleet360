import { useEffect, useState } from "react";

import { useMe } from "../auth/AuthContext";
import { discardOfflineDraft, listOfflineDrafts, saveOfflineDraft, type OfflineDraft } from "../lib/offlineDrafts";

export function OfflineWorkOrderDrafts({ workOrderId, onRestore }: { workOrderId: string; onRestore?: (note: string) => void }) {
  const me = useMe();
  const ownerScope = `${me.workspace_code}:${me.user_account_id}`;
  const [drafts, setDrafts] = useState<OfflineDraft[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void listOfflineDrafts(ownerScope).then((all) => {
      if (active) setDrafts(all.filter((item) => item.workOrderId === workOrderId));
    }).catch(() => { if (active) setError("Brouillons locaux indisponibles sur cet appareil."); });
    return () => { active = false; };
  }, [ownerScope, workOrderId]);

  async function save() {
    setBusy(true); setError("");
    try {
      const draft: OfflineDraft = {
        id: crypto.randomUUID(), ownerScope, kind: "work_order_note", workOrderId,
        note: note.trim(), createdAt: new Date().toISOString(),
      };
      await saveOfflineDraft(draft);
      setDrafts((existing) => [...existing, draft]);
      setNote("");
    } catch { setError("Enregistrement local impossible. Vérifiez l'espace disponible et la note."); }
    finally { setBusy(false); }
  }

  async function discard(id: string) {
    setBusy(true); setError("");
    try {
      await discardOfflineDraft(id, ownerScope);
      setDrafts((existing) => existing.filter((item) => item.id !== id));
    } catch { setError("Suppression locale impossible."); }
    finally { setBusy(false); }
  }

  return <div className="card">
    <h2>Notes locales hors ligne</h2>
    <p className="muted small">Brouillons conservés sur cet appareil, non transmis au serveur. Ils ne constituent pas un compte rendu enregistré. N'y saisissez aucune donnée personnelle ou sensible.</p>
    <label>Note brouillon
      <textarea maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
    </label>
    <button type="button" disabled={busy || !note.trim()} onClick={() => void save()}>Conserver sur cet appareil</button>
    {error && <p role="alert">{error}</p>}
    <ul>{drafts.map((draft) => <li key={draft.id}>
      <p>{draft.note}</p>
      {onRestore && <button type="button" disabled={busy} onClick={() => onRestore(draft.note)}>Reprendre dans le compte rendu</button>}
      <button type="button" disabled={busy} onClick={() => void discard(draft.id)}>Supprimer ce brouillon</button>
    </li>)}</ul>
  </div>;
}
