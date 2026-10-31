import { beforeEach, expect, it, vi } from "vitest";
import { clearOfflineDrafts } from "./offlineDrafts";
import { purgeDraftsForSignedOutUser } from "./offlineLogout";

vi.mock("./offlineDrafts", () => ({ clearOfflineDrafts: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it("efface uniquement les brouillons du workspace et de l'utilisateur sortant", async () => {
  vi.mocked(clearOfflineDrafts).mockResolvedValue(undefined);
  await purgeDraftsForSignedOutUser({
    workspace_code: "minefleet",
    user_account_id: "33333333-3333-4333-8333-333333333333",
  });
  expect(clearOfflineDrafts).toHaveBeenCalledExactlyOnceWith(
    "minefleet:33333333-3333-4333-8333-333333333333",
  );
});

it("propage un échec de suppression pour ne pas déclarer une purge réussie", async () => {
  vi.mocked(clearOfflineDrafts).mockRejectedValue(new Error("Stockage indisponible"));
  await expect(purgeDraftsForSignedOutUser({
    workspace_code: "minefleet",
    user_account_id: "33333333-3333-4333-8333-333333333333",
  })).rejects.toThrow("Stockage indisponible");
});
