import { beforeEach, expect, it, vi } from "vitest";
import { call } from "../api/client";
import { listOfflineDrafts, prepareOfflineNoteTransmission, setOfflineNoteDeliveryStatus, validateOfflineDraft, type OfflineDraft } from "./offlineDrafts";
import { submitPreparedOfflineWorkOrderNote } from "./offlineWorkOrderSubmit";

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(), call: vi.fn(),
}));
vi.mock("./offlineDrafts", () => ({
  listOfflineDrafts: vi.fn(), prepareOfflineNoteTransmission: vi.fn(), setOfflineNoteDeliveryStatus: vi.fn(), validateOfflineDraft: vi.fn(),
}));

const draft: OfflineDraft = {
  id: "11111111-1111-4111-8111-111111111111",
  ownerScope: "minefleet:33333333-3333-4333-8333-333333333333",
  kind: "work_order_note", workOrderId: "44444444-4444-4444-8444-444444444444",
  note: "Inspection", createdAt: "2026-10-31T09:00:00Z",
};
const pending = {
  idempotencyKey: draft.id, ifMatch: '"3"',
  body: { action: "NOTE" as const, diagnosis: "Freins", work_done: "Inspection", parts_note: "" },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listOfflineDrafts).mockResolvedValue([draft]);
  vi.mocked(prepareOfflineNoteTransmission).mockResolvedValue(pending);
  vi.mocked(call).mockResolvedValue({ data: {
    status: "IN_PROGRESS", work_done: null, diagnosis: "Freins", parts_note: "",
  }, etag: '"3"' } as never);
});

it("prépare puis envoie le corps et la clé persistés", async () => {
  await submitPreparedOfflineWorkOrderNote(draft);
  expect(prepareOfflineNoteTransmission).toHaveBeenCalledWith(
    draft.id, draft.ownerScope, '"3"', "Freins", "",
  );
  expect(call).toHaveBeenLastCalledWith("post", "/work-orders/{work_order_id}/progress", {
    path: { work_order_id: draft.workOrderId },
    idempotencyKey: draft.id, ifMatch: '"3"', body: pending.body,
  });
});

it("rejoue une opération déjà préparée sans relire l'OT ni changer son corps", async () => {
  vi.mocked(listOfflineDrafts).mockResolvedValue([{ ...draft, pending }]);
  await submitPreparedOfflineWorkOrderNote(draft);
  expect(call).toHaveBeenCalledOnce();
  expect(call).toHaveBeenCalledWith("post", "/work-orders/{work_order_id}/progress", {
    path: { work_order_id: draft.workOrderId },
    idempotencyKey: draft.id, ifMatch: '"3"', body: pending.body,
  });
  expect(prepareOfflineNoteTransmission).not.toHaveBeenCalled();
});

it("refuse l'envoi quand le brouillon n'existe plus", async () => {
  vi.mocked(listOfflineDrafts).mockResolvedValue([]);
  await expect(submitPreparedOfflineWorkOrderNote(draft)).rejects.toThrow(/introuvable/);
  expect(call).not.toHaveBeenCalled();
  expect(validateOfflineDraft).toHaveBeenCalled();
});

it("conserve la confirmation de transmission après succès", async () => {
  await submitPreparedOfflineWorkOrderNote(draft);
  expect(setOfflineNoteDeliveryStatus).toHaveBeenCalledWith(draft.id, draft.ownerScope, "confirmed");
});

it("ne renvoie pas une transmission déjà confirmée", async () => {
  vi.mocked(listOfflineDrafts).mockResolvedValue([{
    ...draft, pending: { ...pending, deliveryStatus: "confirmed" },
  }]);
  await submitPreparedOfflineWorkOrderNote(draft);
  expect(call).not.toHaveBeenCalled();
});

it("conserve l'état incertain après coupure de transmission", async () => {
  vi.mocked(call).mockResolvedValueOnce({ data: {
    status: "IN_PROGRESS", work_done: null, diagnosis: "Freins", parts_note: "",
  }, etag: '"3"' } as never).mockRejectedValueOnce(new (await import("../api/client")).ApiError(0, {
    code: "NETWORK_ERROR", message_fr: "Coupure réseau", details: null, request_id: null,
  }));
  await expect(submitPreparedOfflineWorkOrderNote(draft)).rejects.toThrow(/incertaine/);
  expect(setOfflineNoteDeliveryStatus).toHaveBeenCalledWith(draft.id, draft.ownerScope, "uncertain");
});
