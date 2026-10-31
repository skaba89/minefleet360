import { call } from "../api/client";

/** Explicit online transfer of a local OT note. Never replay automatically. */
export async function submitOfflineWorkOrderNote(workOrderId: string, note: string): Promise<void> {
  const latest = await call("get", "/work-orders/{work_order_id}", { path: { work_order_id: workOrderId } });
  const order = latest.data;
  if (!latest.etag) throw new Error("Version de l'ordre de travail indisponible. Aucun envoi effectué.");
  if (!["ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"].includes(order.status)) {
    throw new Error("Cet ordre de travail n'accepte plus de compte rendu.");
  }
  if (order.work_done?.trim()) {
    throw new Error("Un compte rendu existe déjà sur le serveur. Reprenez le brouillon manuellement pour éviter de l'écraser.");
  }
  await call("post", "/work-orders/{work_order_id}/progress", {
    path: { work_order_id: workOrderId },
    ifMatch: latest.etag,
    body: {
      action: "NOTE",
      diagnosis: order.diagnosis ?? "",
      work_done: note,
      parts_note: order.parts_note ?? "",
    },
  });
}
