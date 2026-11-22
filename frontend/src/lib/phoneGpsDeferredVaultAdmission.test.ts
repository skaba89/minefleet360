import { describe, expect, it } from "vitest";
import {
  decideDeferredVaultAdmission,
  DEFERRED_VAULT_MAX_DURATION_MS,
  DEFERRED_VAULT_MAX_POINTS,
  type DeferredVaultAdmissionInput,
} from "./phoneGpsDeferredVaultAdmission";

const base: DeferredVaultAdmissionInput = {
  contextValid: true, remainingMs: 60_000,
  pointCount: 0, storedBytes: 0, incomingBytes: 256, byteLimit: 1024,
};

describe("deferred GPS vault admission reference", () => {
  it("admits records within both limits, including exact capacity", () => {
    expect(decideDeferredVaultAdmission(base)).toEqual({ kind: "admit" });
    expect(decideDeferredVaultAdmission({
      ...base, pointCount: DEFERRED_VAULT_MAX_POINTS - 1, storedBytes: 768,
      remainingMs: DEFERRED_VAULT_MAX_DURATION_MS,
    })).toEqual({ kind: "admit" });
  });

  it("refuses new points rather than evicting old ones", () => {
    expect(decideDeferredVaultAdmission({ ...base, pointCount: DEFERRED_VAULT_MAX_POINTS }))
      .toEqual({ kind: "refuse", reason: "points" });
    expect(decideDeferredVaultAdmission({ ...base, storedBytes: 769 }))
      .toEqual({ kind: "refuse", reason: "bytes" });
    expect(decideDeferredVaultAdmission({ ...base, incomingBytes: 1025 }))
      .toEqual({ kind: "refuse", reason: "bytes" });
  });

  it("suspends when context is revoked or the monotonic deadline is unsafe", () => {
    expect(decideDeferredVaultAdmission({ ...base, contextValid: false }))
      .toEqual({ kind: "suspend", reason: "context" });
    for (const remainingMs of [0, -1, NaN, Infinity, DEFERRED_VAULT_MAX_DURATION_MS + 1]) {
      expect(decideDeferredVaultAdmission({ ...base, remainingMs }))
        .toEqual({ kind: "suspend", reason: "deadline" });
    }
  });

  it("fails closed on impossible accounting or missing byte ceiling", () => {
    for (const changes of [
      { pointCount: -1 }, { pointCount: 0.5 }, { pointCount: DEFERRED_VAULT_MAX_POINTS + 1 },
      { storedBytes: -1 }, { storedBytes: 1025 }, { storedBytes: NaN },
      { incomingBytes: 0 }, { incomingBytes: Infinity }, { byteLimit: 0 },
      { byteLimit: Number.MAX_SAFE_INTEGER + 1 },
    ]) {
      expect(decideDeferredVaultAdmission({ ...base, ...changes }))
        .toEqual({ kind: "suspend", reason: "invalid-accounting" });
    }
  });

  it("uses safe integer arithmetic near the maximum representable budget", () => {
    const byteLimit = Number.MAX_SAFE_INTEGER;
    expect(decideDeferredVaultAdmission({ ...base, byteLimit, storedBytes: byteLimit - 1, incomingBytes: 2 }))
      .toEqual({ kind: "refuse", reason: "bytes" });
    expect(decideDeferredVaultAdmission({ ...base, byteLimit, storedBytes: byteLimit - 1, incomingBytes: 1 }))
      .toEqual({ kind: "admit" });
  });
});
