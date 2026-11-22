import { describe, expect, it } from "vitest";
import { decideDeferredRestart, type DeferredRestartEvidence } from "./phoneGpsDeferredRestart";
import { DEFERRED_VAULT_MAX_DURATION_MS } from "./phoneGpsDeferredVaultAdmission";

const base: DeferredRestartEvidence = {
  vault: "healthy", context: "same", authorization: "allowed", remainingMs: 60_000,
};

describe("deferred GPS restart gate", () => {
  it("allows only replay, never autonomous capture, after fresh verification", () => {
    expect(decideDeferredRestart(base)).toEqual({ kind: "replay-eligible", captureAllowed: false });
  });

  it("holds offline or unverified sessions even with a healthy vault", () => {
    expect(decideDeferredRestart({ ...base, authorization: "unavailable" }))
      .toEqual({ kind: "hold", reason: "authorization" });
    expect(decideDeferredRestart({ ...base, context: "unknown" }))
      .toEqual({ kind: "hold", reason: "context" });
    expect(decideDeferredRestart({ ...base, vault: "unknown" }))
      .toEqual({ kind: "hold", reason: "vault" });
  });

  it("requires purge after revocation, context change or interrupted purge", () => {
    expect(decideDeferredRestart({ ...base, authorization: "revoked" }))
      .toEqual({ kind: "purge", reason: "revoked" });
    expect(decideDeferredRestart({ ...base, context: "changed", authorization: "unavailable" }))
      .toEqual({ kind: "purge", reason: "context" });
    for (const vault of ["purge-pending", "orphan"] as const) {
      expect(decideDeferredRestart({ ...base, vault }))
        .toEqual({ kind: "purge", reason: "vault" });
    }
  });

  it("holds an unverifiable deadline and purges a proven expiration", () => {
    for (const remainingMs of [null, NaN, Infinity, DEFERRED_VAULT_MAX_DURATION_MS + 1]) {
      expect(decideDeferredRestart({ ...base, remainingMs }))
        .toEqual({ kind: "hold", reason: "deadline" });
    }
    for (const remainingMs of [0, -1]) {
      expect(decideDeferredRestart({ ...base, remainingMs }))
        .toEqual({ kind: "purge", reason: "expired" });
    }
  });

  it("has no replay work for an empty reconciled vault", () => {
    expect(decideDeferredRestart({ ...base, vault: "empty" })).toEqual({ kind: "idle" });
  });
});
