import { listOfflineDrafts, prepareOfflineNoteTransmission, setOfflineNoteDeliveryStatus, validateOfflineDraft, type OfflineDraft } from "./offlineDrafts";
import { ApiError, call } from "../api/client";

/** Explicit online transfer of a local OT note. Never replay automatically. */
const activeWorkOrders = new Set<string>();
export async function submitOfflineWorkOrderNote(workOrderId: string, note: string): Promise<void> {
  if (activeWorkOrders.has(workOrderId)) throw new Error("Une transmission de cette note OT est déjà en cours.");
  activeWorkOrders.add(workOrderId);
  try {
  const trimmed = note.trim();
  if (!trimmed || trimmed.length > 1000) throw new Error("Note vide ou trop longue : aucun envoi effectué.");
  const latest = await call("get", "/work-orders/{work_order_id}", { path: { work_order_id: workOrderId } });
  const order = latest.data;
  if (!latest.etag) throw new Error("Version de l'ordre de travail indisponible. Aucun envoi effectué.");
  if (!["ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"].includes(order.status)) {
    throw new Error("Cet ordre de travail n'accepte plus de compte rendu.");
  }
  if (order.work_done?.trim()) {
    throw new Error("Un compte rendu existe déjà sur le serveur. Reprenez le brouillon manuellement pour éviter de l'écraser.");
  }
  try {
    await call("post", "/work-orders/{work_order_id}/progress", {
    path: { work_order_id: workOrderId },
    ifMatch: latest.etag,
    body: {
      action: "NOTE",
      diagnosis: order.diagnosis ?? "",
      work_done: trimmed,
      parts_note: order.parts_note ?? "",
    },
    });
  } catch (error) {
    if (error instanceof ApiError && [409, 412, 428].includes(error.status)) {
      throw new Error("Conflit de version ou de statut : rechargez l’OT, vérifiez les changements et reprenez le brouillon manuellement.");
    }
    if (error instanceof ApiError && error.status === 0) {
      throw new Error("Envoi non confirmé : le serveur a peut-être enregistré la note. Rechargez l'OT et vérifiez son compte rendu avant toute nouvelle tentative.");
    }
    throw error;
  }
  } finally {
    activeWorkOrders.delete(workOrderId);
  }
}

/** Replays the exact persisted NOTE command, never rebuilding the payload after an uncertain send. */
export async function submitPreparedOfflineWorkOrderNote(draft: OfflineDraft): Promise<void> {
  const workOrderId = draft.workOrderId;
  if (activeWorkOrders.has(workOrderId)) throw new Error("Une transmission de cette note OT est déjà en cours.");
  activeWorkOrders.add(workOrderId);
  try {
    validateOfflineDraft(draft);
    const stored = (await listOfflineDrafts(draft.ownerScope)).find((item) => item.id === draft.id);
    if (!stored || stored.workOrderId !== workOrderId || stored.note !== draft.note) {
      throw new Error("Brouillon local modifié ou introuvable : aucun envoi effectué.");
    }
    validateOfflineDraft(stored);
    let pending = stored.pending;
    if (pending?.deliveryStatus === "confirmed") return;
    if (!pending) {
      const latest = await call("get", "/work-orders/{work_order_id}", { path: { work_order_id: workOrderId } });
      const order = latest.data;
      if (!latest.etag) throw new Error("Version de l'OT indisponible : aucun envoi effectué.");
      if (!["ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"].includes(order.status)) {
        throw new Error("Cet ordre de travail n'accepte plus de compte rendu.");
      }
      if (order.work_done?.trim()) {
        throw new Error("Un compte rendu existe déjà : reprenez le brouillon manuellement.");
      }
      pending = await prepareOfflineNoteTransmission(
        draft.id, draft.ownerScope, latest.etag, order.diagnosis ?? "", order.parts_note ?? "",
      );
    }
    try {
      await call("post", "/work-orders/{work_order_id}/progress", {
        path: { work_order_id: workOrderId },
        idempotencyKey: pending.idempotencyKey,
        ifMatch: pending.ifMatch,
        body: pending.body,
      });
      try {
        await setOfflineNoteDeliveryStatus(draft.id, draft.ownerScope, "confirmed");
      } catch {
        throw new Error("Note enregistrée sur le serveur, mais confirmation locale impossible. Vérifiez l'OT avant de supprimer le brouillon.");
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 0) {
        try {
          await setOfflineNoteDeliveryStatus(draft.id, draft.ownerScope, "uncertain");
        } catch {
          throw new Error("Envoi incertain et état local non enregistré. Ne supprimez pas le brouillon ; vérifiez l'OT avant de réessayer.");
        }
        throw new Error("Transmission incertaine. La commande est conservée : vérifiez l'OT puis relancez la même opération.");
      }
      throw error;
    }
  } finally {
    activeWorkOrders.delete(workOrderId);
  }
}
