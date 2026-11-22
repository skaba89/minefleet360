import { DEFERRED_VAULT_MAX_DURATION_MS } from "./phoneGpsDeferredVaultAdmission";

export interface DeferredRestartEvidence {
  /** Reconciled local vault, without decrypting positions. */
  vault: "healthy" | "purge-pending" | "orphan" | "unknown" | "empty";
  /** Compared against the original tenant, account, session, site, vehicle and share. */
  context: "same" | "changed" | "unknown";
  /** Fresh server check; unavailable is never equivalent to allowed. */
  authorization: "allowed" | "revoked" | "unavailable";
  /** Null if monotonic validity cannot be established after interruption. */
  remainingMs: number | null;
}

export type DeferredRestartDecision =
  | { kind: "idle" }
  | { kind: "purge"; reason: "vault" | "context" | "revoked" | "expired" }
  | { kind: "hold"; reason: "vault" | "context" | "authorization" | "deadline" }
  | { kind: "replay-eligible"; captureAllowed: false };

/**
 * Reference gate only. No autonomous capture restart and no decryption,
 * scheduling or network requests. Recheck authorization at actual dispatch.
 */
export function decideDeferredRestart(evidence: DeferredRestartEvidence): DeferredRestartDecision {
  if (evidence.vault === "purge-pending" || evidence.vault === "orphan") {
    return { kind: "purge", reason: "vault" };
  }
  if (evidence.context === "changed") return { kind: "purge", reason: "context" };
  if (evidence.authorization === "revoked") return { kind: "purge", reason: "revoked" };
  if (evidence.remainingMs !== null && Number.isFinite(evidence.remainingMs) && evidence.remainingMs <= 0) {
    return { kind: "purge", reason: "expired" };
  }
  if (evidence.vault === "empty") return { kind: "idle" };
  if (evidence.vault !== "healthy") return { kind: "hold", reason: "vault" };
  if (evidence.context !== "same") return { kind: "hold", reason: "context" };
  if (evidence.remainingMs === null || !Number.isFinite(evidence.remainingMs)
    || evidence.remainingMs > DEFERRED_VAULT_MAX_DURATION_MS) {
    return { kind: "hold", reason: "deadline" };
  }
  if (evidence.authorization !== "allowed") return { kind: "hold", reason: "authorization" };
  return { kind: "replay-eligible", captureAllowed: false };
}
