import {
  readDeferredGpsAcknowledgement,
  type DeferredGpsAcknowledgement,
  type DeferredGpsBatch,
} from "./phoneGpsDeferredProtocol";
import { decideDeferredGpsRetry, type DeferredRetryDecision, type DeferredRetryInput } from "./phoneGpsDeferredRetry";

export type DeferredGpsAttemptDecision =
  | Exclude<DeferredRetryDecision, { kind: "acknowledge" }>
  | { kind: "acknowledged"; acknowledgement: DeferredGpsAcknowledgement };

/**
 * Resolve a completed attempt against the original batch and current context.
 * No queue mutation: only an exact ACK can report individual outcomes.
 * An ambiguous response must retry the same body and IDs, never a new batch.
 */
export function resolveDeferredGpsAttempt(
  batch: DeferredGpsBatch,
  input: DeferredRetryInput,
  response: unknown,
): DeferredGpsAttemptDecision {
  const decision = decideDeferredGpsRetry(input);
  if (decision.kind !== "acknowledge") return decision;
  const acknowledgement = readDeferredGpsAcknowledgement(batch, response);
  if (acknowledgement) return { kind: "acknowledged", acknowledgement };

  // A 200 with an incomplete or invalid ACK is indistinguishable from a lost ACK.
  const retry = decideDeferredGpsRetry({ ...input, status: null });
  // The null status cannot enter the acknowledgement branch.
  return retry.kind === "acknowledge" ? { kind: "suspend", reason: "http" } : retry;
}
