import { resolveDeferredGpsAttempt, type DeferredGpsAttemptDecision } from "./phoneGpsDeferredAttempt";
import type { DeferredGpsBatch } from "./phoneGpsDeferredProtocol";
import type { DeferredRetryInput } from "./phoneGpsDeferredRetry";

/** Opaque, unique per dispatch; never reuse after retry, restart or context change. */
export interface DeferredGpsDispatch {
  readonly token: string;
  readonly batch: DeferredGpsBatch;
}

export type DeferredGpsQueuePlan =
  | Exclude<DeferredGpsAttemptDecision, { kind: "acknowledged" }>
  | { kind: "ignore"; reason: "stale" }
  | { kind: "block"; reason: "queue-changed" }
  | { kind: "commit"; confirmedIds: readonly string[]; rejectedCount: number; conflictCount: number; requiresReview: boolean };

/**
 * Pure reference for an atomic queue transaction. Caller must recheck the active
 * dispatch and queue prefix in the same transaction as any removal. No storage.
 * Rejected/conflicting points remain pending explicit disposal policy.
 */
export function planDeferredGpsQueueUpdate(
  active: DeferredGpsDispatch | null,
  completedToken: string,
  queueIds: readonly string[],
  input: DeferredRetryInput,
  response: unknown,
): DeferredGpsQueuePlan {
  if (!active || !active.token || active.token !== completedToken) {
    return { kind: "ignore", reason: "stale" };
  }
  if (!active.batch.ids.length || new Set(queueIds).size !== queueIds.length
    || active.batch.ids.some((id, index) => queueIds[index] !== id)) {
    return { kind: "block", reason: "queue-changed" };
  }
  const decision = resolveDeferredGpsAttempt(active.batch, input, response);
  if (decision.kind !== "acknowledged") return decision;
  const { confirmed, rejected, conflicts } = decision.acknowledgement;
  return {
    kind: "commit",
    confirmedIds: confirmed,
    rejectedCount: rejected.length,
    conflictCount: conflicts.length,
    requiresReview: rejected.length > 0 || conflicts.length > 0,
  };
}
