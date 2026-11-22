/** Reference admission policy for the candidate native vault, not a PWA buffer. */
export const DEFERRED_VAULT_MAX_POINTS = 4320;
export const DEFERRED_VAULT_MAX_DURATION_MS = 12 * 60 * 60 * 1000;

export interface DeferredVaultAdmissionInput {
  contextValid: boolean;
  /** Monotonic remaining validity, never extended locally. */
  remainingMs: number;
  pointCount: number;
  storedBytes: number;
  /** Complete encrypted record cost, including overhead. */
  incomingBytes: number;
  /** Measured/configured ceiling; no default until the native pilot. */
  byteLimit: number;
}

export type DeferredVaultAdmission =
  | { kind: "admit" }
  | { kind: "refuse"; reason: "points" | "bytes" }
  | { kind: "suspend"; reason: "context" | "deadline" | "invalid-accounting" };

function isCount(value: number): boolean {
  return Number.isSafeInteger(value) && value >= 0;
}

/**
 * Never evict old points to admit new ones. The future vault must recheck
 * counters and authorization atomically with the encrypted record commit.
 */
export function decideDeferredVaultAdmission(input: DeferredVaultAdmissionInput): DeferredVaultAdmission {
  if (!input.contextValid) return { kind: "suspend", reason: "context" };
  if (!Number.isFinite(input.remainingMs) || input.remainingMs <= 0
    || input.remainingMs > DEFERRED_VAULT_MAX_DURATION_MS) {
    return { kind: "suspend", reason: "deadline" };
  }
  if (!isCount(input.pointCount) || input.pointCount > DEFERRED_VAULT_MAX_POINTS
    || !isCount(input.storedBytes) || !isCount(input.byteLimit) || input.byteLimit === 0
    || !isCount(input.incomingBytes) || input.incomingBytes === 0
    || input.storedBytes > input.byteLimit) {
    return { kind: "suspend", reason: "invalid-accounting" };
  }
  if (input.pointCount === DEFERRED_VAULT_MAX_POINTS) return { kind: "refuse", reason: "points" };
  // Subtraction avoids overflow from adding two individually safe integers.
  if (input.incomingBytes > input.byteLimit - input.storedBytes) {
    return { kind: "refuse", reason: "bytes" };
  }
  return { kind: "admit" };
}
