import { describe, expect, it } from "vitest";

import { identityKey, mayResumeOfflineQueue } from "./offline-scope";

const original = { tenantId: "tenant-a", userId: "driver-a", siteId: "site-1" };

describe("cloisonnement de la file hors ligne", () => {
  it("accepte uniquement le même compte dans le même site et tenant", () => {
    expect(mayResumeOfflineQueue(original, { ...original })).toBe(true);
    expect(mayResumeOfflineQueue(original, { ...original, siteId: "site-2" })).toBe(false);
    expect(mayResumeOfflineQueue(original, { ...original, userId: "driver-b" })).toBe(false);
    expect(mayResumeOfflineQueue(original, { ...original, tenantId: "tenant-b" })).toBe(false);
  });

  it("interdit le rejeu sans session et sans identité complète", () => {
    expect(mayResumeOfflineQueue(original, null)).toBe(false);
    expect(mayResumeOfflineQueue(original, { ...original, userId: "" })).toBe(false);
    expect(() => identityKey({ ...original, tenantId: "" })).toThrow("incomplète");
  });

  it("ne confond pas les identifiants contenant des séparateurs", () => {
    expect(
      identityKey({ tenantId: "a:b", userId: "c", siteId: "d" }),
    ).not.toBe(identityKey({ tenantId: "a", userId: "b:c", siteId: "d" }));
  });
});
