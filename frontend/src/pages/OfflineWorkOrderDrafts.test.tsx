import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { clearOfflineDrafts, listOfflineDrafts } from "../lib/offlineDrafts";
import { OfflineWorkOrderDrafts } from "./OfflineWorkOrderDrafts";

vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ workspace_code: "minefleet", user_account_id: "33333333-3333-4333-8333-333333333333" }),
}));
vi.mock("../lib/offlineDrafts", () => ({
  clearOfflineDrafts: vi.fn(),
  discardOfflineDraft: vi.fn(),
  listOfflineDrafts: vi.fn(),
  saveOfflineDraft: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listOfflineDrafts).mockResolvedValue([{
    id: "11111111-1111-4111-8111-111111111111",
    ownerScope: "minefleet:33333333-3333-4333-8333-333333333333",
    workOrderId: "44444444-4444-4444-8444-444444444444",
    kind: "work_order_note",
    note: "Vérifier la pompe",
    createdAt: "2026-10-31T09:00:00Z",
  }]);
  vi.mocked(clearOfflineDrafts).mockResolvedValue(undefined);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("ne supprime rien sans confirmation de l'utilisateur", async () => {
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<OfflineWorkOrderDrafts workOrderId="44444444-4444-4444-8444-444444444444" />);
  await screen.findByText("Vérifier la pompe");
  fireEvent.click(screen.getByRole("button", { name: "Effacer tous mes brouillons locaux" }));
  expect(clearOfflineDrafts).not.toHaveBeenCalled();
});

it("efface les brouillons du compte actif après confirmation", async () => {
  vi.stubGlobal("confirm", vi.fn(() => true));
  render(<OfflineWorkOrderDrafts workOrderId="44444444-4444-4444-8444-444444444444" />);
  await screen.findByText("Vérifier la pompe");
  fireEvent.click(screen.getByRole("button", { name: "Effacer tous mes brouillons locaux" }));
  await waitFor(() => expect(clearOfflineDrafts).toHaveBeenCalledWith(
    "minefleet:33333333-3333-4333-8333-333333333333",
  ));
  await waitFor(() => expect(screen.queryByText("Vérifier la pompe")).toBeNull());
});
