import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { syncAccount, type SyncDeps } from "./hseOfflineSync";
import type { OutboxEntry } from "./offline-outbox";
import type { LockManagerLike } from "./offline-sync-lock";

const account = { tenantId: "espace-a", userId: "user-a" };
const NOW = Date.parse("2026-11-02T10:00:00Z");

function entry(id: string, extra: Partial<OutboxEntry> = {}): OutboxEntry {
  return {
    operationId: id,
    tenantId: "espace-a",
    userId: "user-a",
    siteId: "site-1",
    endpoint: "/hse/incidents",
    payload: { site_id: "site-1", title: `Incident ${id}` },
    createdAt: `2026-11-02T09:0${id.length}:00Z`,
    status: "pending",
    attempts: 0,
    ...extra,
  };
}

function apiError(status: number, code: string): ApiError {
  return new ApiError(status, { code, message_fr: code, details: null, request_id: null });
}

/** Verrou exclusif en mémoire, fidèle à `ifAvailable: true` (refus immédiat si déjà tenu). */
function memoryLocks(): LockManagerLike {
  const held = new Set<string>();
  return {
    async request(name, _options, callback) {
      if (held.has(name)) return callback(null);
      held.add(name);
      try {
        return await callback({ name });
      } finally {
        held.delete(name);
      }
    },
  };
}

function harness(entries: OutboxEntry[], send: SyncDeps["send"]) {
  const store = new Map(entries.map((e) => [e.operationId, { ...e }]));
  const deps: SyncDeps = {
    list: async () => [...store.values()].sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    update: async (e) => {
      store.set(e.operationId, { ...e });
    },
    send: vi.fn(send),
    locks: memoryLocks(),
    now: () => NOW,
  };
  return { store, deps };
}

describe("synchronisation des déclarations HSE hors ligne", () => {
  it("marque synchronisée seulement après l'accusé de réception serveur, avec la clé stable", async () => {
    const { store, deps } = harness([entry("a")], async (e) => ({ id: `srv-${e.operationId}`, reference: "HSE-000042" }));
    const result = await syncAccount(account, deps);
    expect(result).toEqual({ kind: "done", synchronized: 1, rejected: 0, waiting: 0 });
    expect(deps.send).toHaveBeenCalledWith(expect.objectContaining({ operationId: "a", payload: { site_id: "site-1", title: "Incident a" } }));
    expect(store.get("a")).toMatchObject({ status: "synchronized", serverReference: "HSE-000042", serverId: "srv-a", attempts: 1 });
  });

  it("une coupure réseau garde l'opération en attente et préserve l'ordre de la file", async () => {
    const { store, deps } = harness([entry("a"), entry("bb")], async () => {
      throw apiError(0, "NETWORK_ERROR");
    });
    const result = await syncAccount(account, deps);
    expect(result).toEqual({ kind: "done", synchronized: 0, rejected: 0, waiting: 2 });
    expect(deps.send).toHaveBeenCalledOnce();
    expect(store.get("a")).toMatchObject({ status: "pending", attempts: 1, errorCode: "NETWORK_ERROR" });
    expect(store.get("a")?.retryAt).toBeGreaterThan(NOW);
    expect(store.get("bb")).toMatchObject({ status: "pending", attempts: 0 });
  });

  it.each([
    [429, "RATE_LIMITED"],
    [503, "SERVICE_BUSY"],
    [500, "INTERNAL_ERROR"],
  ])("%i est transitoire : nouvel essai différé", async (status, code) => {
    const { store, deps } = harness([entry("a")], async () => {
      throw apiError(status, code);
    });
    await syncAccount(account, deps);
    expect(store.get("a")).toMatchObject({ status: "pending", errorCode: code });
    expect(store.get("a")?.retryAt).toBeGreaterThan(NOW);
  });

  it.each([
    [403, "PERMISSION_DENIED"],
    [409, "CONFLICT"],
    [422, "REFERENCE_NOT_FOUND"],
    [422, "IDEMPOTENCY_KEY_REUSED"],
  ])("%i %s est un rejet définitif affiché, la file continue", async (status, code) => {
    const send = vi.fn<SyncDeps["send"]>()
      .mockRejectedValueOnce(apiError(status, code))
      .mockResolvedValueOnce({ id: "srv-b", reference: "HSE-000043" });
    const { store, deps } = harness([entry("a"), entry("bb")], send);
    const result = await syncAccount(account, deps);
    expect(result).toEqual({ kind: "done", synchronized: 1, rejected: 1, waiting: 0 });
    expect(store.get("a")).toMatchObject({ status: "rejected", errorCode: code });
    expect(store.get("bb")).toMatchObject({ status: "synchronized" });
  });

  it("une session expirée interrompt la passe sans rien perdre", async () => {
    const { store, deps } = harness([entry("a"), entry("bb")], async () => {
      throw apiError(401, "AUTH_REQUIRED");
    });
    expect(await syncAccount(account, deps)).toEqual({ kind: "reauthenticate" });
    expect(deps.send).toHaveBeenCalledOnce();
    expect(store.get("a")).toMatchObject({ status: "pending", errorCode: "SESSION_EXPIRED" });
    expect(store.get("bb")).toMatchObject({ status: "pending" });
  });

  it("respecte le délai de nouvel essai", async () => {
    const { deps } = harness([entry("a", { retryAt: NOW + 5_000, attempts: 2 })], async () => ({ id: "x", reference: "HSE-1" }));
    expect(await syncAccount(account, deps)).toEqual({ kind: "done", synchronized: 0, rejected: 0, waiting: 1 });
    expect(deps.send).not.toHaveBeenCalled();
  });

  it("rejoue une opération restée « en cours » après fermeture du navigateur", async () => {
    const { store, deps } = harness([entry("a", { status: "syncing", attempts: 1 })], async () => ({ id: "srv-a", reference: "HSE-000044" }));
    await syncAccount(account, deps);
    expect(deps.send).toHaveBeenCalledOnce();
    expect(store.get("a")).toMatchObject({ status: "synchronized", attempts: 2 });
  });

  it("n'envoie ni les opérations terminées ni celles d'un autre compte", async () => {
    const { deps } = harness(
      [
        entry("a", { status: "synchronized", serverReference: "HSE-1" }),
        entry("bb", { status: "rejected" }),
        entry("ccc", { userId: "user-b" }),
        entry("dddd", { tenantId: "espace-b" }),
      ],
      async () => ({ id: "x", reference: "HSE-2" }),
    );
    await syncAccount(account, deps);
    expect(deps.send).not.toHaveBeenCalled();
  });

  it("un accusé de réception incomplet n'est pas une synchronisation", async () => {
    const { store, deps } = harness([entry("a")], async () => {
      throw new Error("Accusé de réception serveur incomplet");
    });
    await syncAccount(account, deps);
    expect(store.get("a")?.status).toBe("pending");
  });

  it("deux onglets : une seule passe envoie, l'autre constate le verrou", async () => {
    let release: (value: { id: string; reference: string }) => void = () => undefined;
    const { deps } = harness([entry("a")], () => new Promise((resolve) => { release = resolve; }));
    const first = syncAccount(account, deps);
    await vi.waitFor(() => expect(deps.send).toHaveBeenCalledOnce());
    expect(await syncAccount(account, deps)).toEqual({ kind: "locked" });
    release({ id: "srv-a", reference: "HSE-000045" });
    expect(await first).toMatchObject({ kind: "done", synchronized: 1 });
    expect(deps.send).toHaveBeenCalledOnce();
  });

  it("sans Web Locks, refuse de synchroniser plutôt que risquer un double envoi", async () => {
    const { deps } = harness([entry("a")], async () => ({ id: "x", reference: "HSE-1" }));
    expect(await syncAccount(account, { ...deps, locks: null })).toEqual({ kind: "locked" });
    expect(deps.send).not.toHaveBeenCalled();
  });
});
