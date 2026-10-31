import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { listOfflineDrafts, type OfflineDraft } from "../lib/offlineDrafts";
import { OfflineWorkOrderDrafts } from "./OfflineWorkOrderDrafts";

vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ workspace_code: "minefleet", user_account_id: "33333333-3333-4333-8333-333333333333" }),
}));
vi.mock("../lib/offlineDrafts", () => ({
  listOfflineDrafts: vi.fn(), clearOfflineDrafts: vi.fn(), discardOfflineDraft: vi.fn(), saveOfflineDraft: vi.fn(),
}));
const draft: OfflineDraft = {
  id: "11111111-1111-4111-8111-111111111111",
  ownerScope: "minefleet:33333333-3333-4333-8333-333333333333",
  kind: "work_order_note",
  workOrderId: "44444444-4444-4444-8444-444444444444",
  note: "Inspection", createdAt: "2026-10-31T09:00:00Z",
};

beforeEach(() => {
  vi.stubGlobal("navigator", { onLine: true });
  vi.mocked(listOfflineDrafts).mockResolvedValue([draft]);
});

afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks();
});

it("désactive puis réactive le bouton selon les événements réseau du navigateur", async () => {
  render(<OfflineWorkOrderDrafts workOrderId={draft.workOrderId} onSubmit={vi.fn()} />);
  const button = await screen.findByRole("button", { name: "Transmettre cette note en ligne" });
  expect((button as HTMLButtonElement).disabled).toBe(false);
  vi.stubGlobal("navigator", { onLine: false });
  fireEvent(window, new Event("offline"));
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(true));
  vi.stubGlobal("navigator", { onLine: true });
  fireEvent(window, new Event("online"));
  await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
});

it("réaffiche l'état IndexedDB après un envoi échoué", async () => {
  const updated: OfflineDraft = {
    ...draft, pending: {
      idempotencyKey: draft.id, ifMatch: '"3"', deliveryStatus: "uncertain",
      body: { action: "NOTE", diagnosis: "", work_done: draft.note, parts_note: "" },
    },
  };
  vi.mocked(listOfflineDrafts).mockResolvedValueOnce([draft]).mockResolvedValue([updated]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const onSubmit = vi.fn().mockRejectedValue(new Error("Envoi incertain"));
  render(<OfflineWorkOrderDrafts workOrderId={draft.workOrderId} onSubmit={onSubmit} />);
  fireEvent.click(await screen.findByRole("button", { name: "Transmettre cette note en ligne" }));
  await screen.findByText("Transmission incertaine — vérifier l’OT");
  expect(screen.getByRole("alert").textContent).toContain("Envoi incertain");
});
