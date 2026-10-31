import { useEffect, useState } from "react";

import { useMe } from "../auth/AuthContext";
import { useConnectivity } from "../lib/connectivity";
import { clearOfflineDrafts, discardOfflineDraft, listOfflineDrafts, saveOfflineDraft, type OfflineDraft } from "../lib/offlineDrafts";

export function OfflineWorkOrderDrafts({ workOrderId, onRestore, onSubmit }: { workOrderId: string; onRestore?: (note: string) => void; onSubmit?: (draft: OfflineDraft) => Promise<void> }) {
  const me = useMe();
  const online = useConnectivity();
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

  async function submit(draft: OfflineDraft) {
    if (!window.confirm("Transmettre volontairement cette note au serveur ? Le brouillon restera sur cet appareil.")) return;
    setBusy(true); setError("");
    try {
      await onSubmit?.(draft);
      setDrafts((await listOfflineDrafts(ownerScope)).filter((item) => item.workOrderId === workOrderId));
      setError("Note transmise. Le brouillon local est conservé : vous pouvez le supprimer après vérification.");
    } catch (err) {
      try {
        setDrafts((await listOfflineDrafts(ownerScope)).filter((item) => item.workOrderId === workOrderId));
      } catch { /* Priorité au message original d'erreur d'envoi. */ }
      setError(err instanceof Error ? err.message : "Envoi non confirmé. Vérifiez l'OT avant de réessayer.");
    } finally { setBusy(false); }
  }

  async function discard(id: string) {
    setBusy(true); setError("");
    try {
      await discardOfflineDraft(id, ownerScope);
      setDrafts((existing) => existing.filter((item) => item.id !== id));
    } catch { setError("Suppression locale impossible."); }
    finally { setBusy(false); }
  }

  async function purge() {
    if (!window.confirm("Supprimer définitivement tous vos brouillons locaux de cet espace de travail sur cet appareil ?")) return;
    setBusy(true); setError("");
    try {
      await clearOfflineDrafts(ownerScope);
      setDrafts([]);
      setNote("");
    } catch {
      setError("Effacement incomplet : certains brouillons peuvent subsister. Réessayez.");
      try {
        const remaining = await listOfflineDrafts(ownerScope);
        setDrafts(remaining.filter((item) => item.workOrderId === workOrderId));
      } catch { /* Les données n'ont pas été déclarées effacées. */ }
    } finally { setBusy(false); }
  }

  return <div className="card">
    <h2>Notes locales hors ligne</h2>
    <p className="muted small" role="status">{online ? "Connexion réseau détectée. Transmissions manuelles uniquement." : "Sans connexion : brouillons conservés, transmission suspendue."}</p>
    <p className="muted small">Brouillons conservés sur cet appareil, non transmis au serveur. Ils ne constituent pas un compte rendu enregistré. N'y saisissez aucune donnée personnelle ou sensible.</p>
    <label>Note brouillon
      <textarea maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
    </label>
    <button type="button" disabled={busy || !note.trim()} onClick={() => void save()}>Conserver sur cet appareil</button>
    {error && <p role="alert">{error}</p>}
    <div className="toolbar"><button type="button" className="danger" disabled={busy} onClick={() => void purge()}>Effacer tous mes brouillons locaux</button></div>
    <ul>{drafts.map((draft) => <li key={draft.id}>
      <p>{draft.note}</p>
      <p className="muted small">{draft.pending?.deliveryStatus === "confirmed" ? "Transmission confirmée" : draft.pending?.deliveryStatus === "uncertain" ? "Transmission incertaine — vérifier l’OT" : draft.pending ? "Commande préparée, non confirmée" : "Brouillon non transmis"}</p>
      {onRestore && <button type="button" disabled={busy} onClick={() => onRestore(draft.note)}>Reprendre dans le compte rendu</button>}
      {onSubmit && <button type="button" disabled={busy || !online || draft.pending?.deliveryStatus === "confirmed"} onClick={() => void submit(draft)}>Transmettre cette note en ligne</button>}
      <button type="button" disabled={busy} onClick={() => void discard(draft.id)}>Supprimer ce brouillon</button>
    </li>)}</ul>
  </div>;
}
