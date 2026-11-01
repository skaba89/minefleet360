import { describe, expect, it, vi } from "vitest";

import { withExclusiveOfflineSync, type LockManagerLike } from "./offline-sync-lock";

const identity = { tenantId: "tenant", userId: "user", siteId: "site" };

describe("verrou exclusif de synchronisation", () => {
  it("refuse fermé si Web Locks n'est pas disponible", async () => {
    const work = vi.fn(async () => "sent");
    expect(await withExclusiveOfflineSync(identity, null, work)).toEqual({ acquired: false });
    expect(work).not.toHaveBeenCalled();
  });

  it("ne lance pas de travail si le verrou est déjà occupé", async () => {
    const locks: LockManagerLike = {
      request: async (_name, _options, callback) => callback(null),
    };
    const work = vi.fn(async () => "sent");
    expect(await withExclusiveOfflineSync(identity, locks, work)).toEqual({ acquired: false });
    expect(work).not.toHaveBeenCalled();
  });

  it("exécute le travail uniquement sous verrou exclusif", async () => {
    const names: string[] = [];
    const locks: LockManagerLike = {
      request: async (name, options, callback) => {
        names.push(name);
        expect(options).toEqual({ mode: "exclusive", ifAvailable: true });
        return callback({ name });
      },
    };
    const work = vi.fn(async () => "sent");
    expect(await withExclusiveOfflineSync(identity, locks, work)).toEqual({
      acquired: true, result: "sent",
    });
    expect(work).toHaveBeenCalledOnce();
    expect(names[0]).toContain("minefleet-offline-sync:");
  });

  it("ne supprime pas les erreurs du travail", async () => {
    const locks: LockManagerLike = {
      request: async (name, _options, callback) => callback({ name }),
    };
    await expect(withExclusiveOfflineSync(identity, locks, async () => {
      throw new Error("réseau indisponible");
    })).rejects.toThrow("réseau indisponible");
  });

  it("refuse une identité incomplète avant acquisition", async () => {
    const work = vi.fn(async () => undefined);
    await expect(withExclusiveOfflineSync({ ...identity, userId: "" }, null, work)).rejects.toThrow(
      "Identité terrain incomplète",
    );
  });
});
