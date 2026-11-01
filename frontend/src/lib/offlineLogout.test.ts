import { beforeEach, expect, it, vi } from "vitest";
import { clearOfflineDrafts } from "./offlineDrafts";
import { purgeOutbox } from "./offline-outbox";
import { purgeDraftsForSignedOutUser } from "./offlineLogout";

vi.mock("./offlineDrafts", () => ({ clearOfflineDrafts: vi.fn() }));
vi.mock("./offline-outbox", () => ({ purgeOutbox: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(clearOfflineDrafts).mockResolvedValue(undefined);
  vi.mocked(purgeOutbox).mockResolvedValue(undefined);
});

const profile = {
  workspace_code: "minefleet",
  user_account_id: "33333333-3333-4333-8333-333333333333",
};

it("purge les brouillons du compte et toute la file locale", async () => {
  await purgeDraftsForSignedOutUser(profile);
  expect(clearOfflineDrafts).toHaveBeenCalledExactlyOnceWith(
    "minefleet:33333333-3333-4333-8333-333333333333",
  );
  expect(purgeOutbox).toHaveBeenCalledOnce();
});

it("tente toujours la purge outbox si les brouillons échouent", async () => {
  vi.mocked(clearOfflineDrafts).mockRejectedValue(new Error("Stockage indisponible"));
  await expect(purgeDraftsForSignedOutUser(profile)).rejects.toThrow("pas pu être confirmée");
  expect(purgeOutbox).toHaveBeenCalledOnce();
});

it("signale l'échec outbox sans déclarer la purge réussie", async () => {
  vi.mocked(purgeOutbox).mockRejectedValue(new Error("IndexedDB bloqué"));
  await expect(purgeDraftsForSignedOutUser(profile)).rejects.toThrow("pas pu être confirmée");
  expect(clearOfflineDrafts).toHaveBeenCalledOnce();
});
