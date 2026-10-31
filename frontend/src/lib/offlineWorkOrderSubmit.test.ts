import { beforeEach, expect, it, vi } from "vitest";
import { ApiError, call } from "../api/client";
import { submitOfflineWorkOrderNote } from "./offlineWorkOrderSubmit";

vi.mock("../api/client", () => ({ call: vi.fn() }));
const id = "44444444-4444-4444-8444-444444444444";
const server = { status: "IN_PROGRESS", work_done: null, diagnosis: "Pompe", parts_note: "Joint" };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(call).mockResolvedValue({ data: server, etag: '"3"' } as never);
});

it("recharge l'OT et utilise la version serveur avant une transmission explicite", async () => {
  await submitOfflineWorkOrderNote(id, "Inspection faite");
  expect(call).toHaveBeenCalledTimes(2);
  expect(call).toHaveBeenLastCalledWith("post", "/work-orders/{work_order_id}/progress", {
    path: { work_order_id: id }, ifMatch: '"3"',
    body: { action: "NOTE", diagnosis: "Pompe", work_done: "Inspection faite", parts_note: "Joint" },
  });
});

it("refuse d'écraser un compte rendu déjà présent", async () => {
  vi.mocked(call).mockResolvedValue({ data: { ...server, work_done: "Déjà enregistré" }, etag: '"3"' } as never);
  await expect(submitOfflineWorkOrderNote(id, "Nouveau")).rejects.toThrow(/existe déjà/);
  expect(call).toHaveBeenCalledOnce();
});

it("refuse les états clos et les OT sans version", async () => {
  vi.mocked(call).mockResolvedValueOnce({ data: { ...server, status: "CLOSED" }, etag: '"3"' } as never);
  await expect(submitOfflineWorkOrderNote(id, "Nouvelle note")).rejects.toThrow(/n'accepte plus/);
  vi.mocked(call).mockResolvedValueOnce({ data: server, etag: null } as never);
  await expect(submitOfflineWorkOrderNote(id, "Nouvelle note")).rejects.toThrow(/Version/);
  expect(call).toHaveBeenCalledTimes(2);
});

it("signale un résultat ambigu après une panne réseau sans renvoyer la mutation", async () => {
  vi.mocked(call).mockResolvedValueOnce({ data: server, etag: '"3"' } as never);
  vi.mocked(call).mockRejectedValueOnce(new ApiError(0, {
    code: "NETWORK_ERROR", message_fr: "Réseau interrompu", details: null, request_id: null,
  }));
  await expect(submitOfflineWorkOrderNote(id, "Inspection")).rejects.toThrow(/peut-être enregistré/);
  expect(call).toHaveBeenCalledTimes(2);
});
