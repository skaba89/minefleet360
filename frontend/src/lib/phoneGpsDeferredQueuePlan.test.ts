import { describe, expect, it } from "vitest";
import { planDeferredGpsQueueUpdate, type DeferredGpsDispatch } from "./phoneGpsDeferredQueuePlan";
import type { DeferredRetryInput } from "./phoneGpsDeferredRetry";

const a = "00000000-0000-4000-8000-000000000001";
const b = "00000000-0000-4000-8000-000000000002";
const c = "00000000-0000-4000-8000-000000000003";
const active: DeferredGpsDispatch = { token: "attempt-2", batch: { ids: [a, b], body: "" } };
const queue = Object.freeze([a, b, c]);
const input: DeferredRetryInput = {
  status: 200, attempts: 2, remainingMs: 120_000, contextValid: true, wallNowMs: 0,
};
const ack = { [a]: "accepted", [b]: "duplicate" };

describe("deferred GPS queue transaction plan", () => {
  it("ignores late responses from a prior dispatch or cleared context", () => {
    expect(planDeferredGpsQueueUpdate(active, "attempt-1", queue, input, ack))
      .toEqual({ kind: "ignore", reason: "stale" });
    expect(planDeferredGpsQueueUpdate(null, "attempt-2", queue, input, ack))
      .toEqual({ kind: "ignore", reason: "stale" });
  });

  it("allows a new tail while confirming only the original batch", () => {
    expect(planDeferredGpsQueueUpdate(active, active.token, queue, input, ack)).toEqual({
      kind: "commit", confirmedIds: [a, b], rejectedCount: 0, conflictCount: 0, requiresReview: false,
    });
    expect(queue).toEqual([a, b, c]);
  });

  it("blocks missing, reordered or duplicated queue identities", () => {
    for (const ids of [[a], [b, a, c], [a, b, c, a], []]) {
      expect(planDeferredGpsQueueUpdate(active, active.token, ids, input, ack))
        .toEqual({ kind: "block", reason: "queue-changed" });
    }
  });

  it("retains rejected and conflicted points for review", () => {
    for (const status of ["rejected", "conflict"]) {
      expect(planDeferredGpsQueueUpdate(active, active.token, queue, input, { [a]: "accepted", [b]: status }))
        .toEqual({
          kind: "commit", confirmedIds: [a], rejectedCount: status === "rejected" ? 1 : 0,
          conflictCount: status === "conflict" ? 1 : 0, requiresReview: true,
        });
    }
  });

  it("never plans removals on ambiguous ACK or revoked context", () => {
    expect(planDeferredGpsQueueUpdate(active, active.token, queue, input, { [a]: "accepted" }))
      .toEqual({ kind: "retry", delayMs: 2000 });
    expect(planDeferredGpsQueueUpdate(active, active.token, queue, { ...input, contextValid: false }, ack))
      .toEqual({ kind: "suspend", reason: "context" });
  });
});
