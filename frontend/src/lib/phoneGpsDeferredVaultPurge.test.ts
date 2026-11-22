import { describe, expect, it } from "vitest";
import { nextDeferredVaultPurgeStep, type DeferredVaultPurgeEvidence } from "./phoneGpsDeferredVaultPurge";

const initial: DeferredVaultPurgeEvidence = {
  quiesced: false, tombstone: "absent", key: "present", ciphertext: "present",
};

describe("deferred GPS vault purge reference", () => {
  it("stops all capture and dispatch before touching the vault", () => {
    expect(nextDeferredVaultPurgeStep(initial)).toBe("quiesce");
    expect(nextDeferredVaultPurgeStep({ ...initial, key: "absent", ciphertext: "absent" })).toBe("quiesce");
  });

  it("requires a durable tombstone before destroying the key", () => {
    expect(nextDeferredVaultPurgeStep({ ...initial, quiesced: true })).toBe("persist-tombstone");
  });

  it("destroys the key before deleting ciphertext", () => {
    const stopped = { ...initial, quiesced: true, tombstone: "present" } as const;
    expect(nextDeferredVaultPurgeStep(stopped)).toBe("destroy-key");
    expect(nextDeferredVaultPurgeStep({ ...stopped, key: "absent" })).toBe("delete-ciphertext");
    expect(nextDeferredVaultPurgeStep({ ...stopped, key: "absent", ciphertext: "absent" })).toBe("complete");
  });

  it("recovers when interrupted after key or ciphertext deletion", () => {
    const stopped = { ...initial, quiesced: true, tombstone: "present" } as const;
    expect(nextDeferredVaultPurgeStep({ ...stopped, key: "absent" })).toBe("delete-ciphertext");
    expect(nextDeferredVaultPurgeStep({ ...stopped, ciphertext: "absent" })).toBe("destroy-key");
  });

  it("does not interpret unknown evidence as absence", () => {
    const stopped = { ...initial, quiesced: true, tombstone: "present" } as const;
    expect(nextDeferredVaultPurgeStep({ ...stopped, tombstone: "unknown" })).toBe("verify");
    expect(nextDeferredVaultPurgeStep({ ...stopped, key: "unknown" })).toBe("verify");
    expect(nextDeferredVaultPurgeStep({ ...stopped, key: "absent", ciphertext: "unknown" })).toBe("verify");
  });
});
