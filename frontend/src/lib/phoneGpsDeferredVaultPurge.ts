/** Pure recovery plan for a vault already selected for irreversible purge. */
export interface DeferredVaultPurgeEvidence {
  /** Capture and sender stopped, with active dispatch tokens invalidated. */
  quiesced: boolean;
  /** Durable tombstone preventing any reopening, including after restart. */
  tombstone: "present" | "absent" | "unknown";
  /** Verified against the original vault's exact key alias. */
  key: "present" | "absent" | "unknown";
  /** Verified against the original vault's exact encrypted storage. */
  ciphertext: "present" | "absent" | "unknown";
}

export type DeferredVaultPurgeStep =
  | "quiesce"
  | "persist-tombstone"
  | "destroy-key"
  | "delete-ciphertext"
  | "verify"
  | "complete";

/**
 * No I/O: every step requires fresh evidence before advancing. The future
 * executor must serialize the purge with all vault access. Never remove the
 * tombstone here or recreate a key for a purged vault.
 */
export function nextDeferredVaultPurgeStep(evidence: DeferredVaultPurgeEvidence): DeferredVaultPurgeStep {
  if (!evidence.quiesced) return "quiesce";
  if (evidence.tombstone === "unknown") return "verify";
  if (evidence.tombstone !== "present") return "persist-tombstone";
  if (evidence.key === "unknown") return "verify";
  if (evidence.key !== "absent") return "destroy-key";
  if (evidence.ciphertext === "unknown") return "verify";
  if (evidence.ciphertext !== "absent") return "delete-ciphertext";
  return "complete";
}
