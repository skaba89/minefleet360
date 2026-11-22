import { describe, expect, it } from "vitest";
import { resolveDeferredGpsAttempt } from "./phoneGpsDeferredAttempt";
import type { DeferredGpsBatch } from "./phoneGpsDeferredProtocol";
import type { DeferredRetryInput } from "./phoneGpsDeferredRetry";

const a = "00000000-0000-4000-8000-000000000001";
const b = "00000000-0000-4000-8000-000000000002";
const c = "00000000-0000-4000-8000-000000000003";
const batch: DeferredGpsBatch = Object.freeze({
  ids: Object.freeze([a, b, c]),
  body: '{"points":[]}',
});
const base: DeferredRetryInput = {
  status: 200, attempts: 1, remainingMs: 120_000, contextValid: true, wallNowMs: 0,
};
const ack = { [a]: "duplicate", [b]: "rejected", [c]: "conflict" };

describe("deferred GPS attempt resolution", () => {
  it("reports exact individual outcomes even on the final attempt", () => {
    expect(resolveDeferredGpsAttempt(batch, { ...base, attempts: 8 }, ack)).toEqual({
      kind: "acknowledged",
      acknowledgement: { confirmed: [a], rejected: [b], conflicts: [c] },
    });
  });

  it("retries ambiguous success without confirming or mutating any point", () => {
    for (const response of [null, {}, { [a]: "accepted" }, { ...ack, extra: "accepted" },
      { ...ack, [b]: "unknown" }, [ack]]) {
      expect(resolveDeferredGpsAttempt(batch, base, response)).toEqual({ kind: "retry", delayMs: 1000 });
    }
    expect(batch.ids).toEqual([a, b, c]);
    expect(batch.body).toBe('{"points":[]}');
  });

  it("never applies an ACK after expiry or context revocation", () => {
    expect(resolveDeferredGpsAttempt(batch, { ...base, contextValid: false }, ack))
      .toEqual({ kind: "suspend", reason: "context" });
    expect(resolveDeferredGpsAttempt(batch, { ...base, remainingMs: 0 }, ack))
      .toEqual({ kind: "suspend", reason: "expired" });
  });

  it("honors the retry limit and deadline on malformed acknowledgements", () => {
    expect(resolveDeferredGpsAttempt(batch, { ...base, attempts: 8 }, {}))
      .toEqual({ kind: "suspend", reason: "attempts" });
    expect(resolveDeferredGpsAttempt(batch, { ...base, attempts: 0 }, {}))
      .toEqual({ kind: "suspend", reason: "attempts" });
    expect(resolveDeferredGpsAttempt(batch, { ...base, remainingMs: 1000 }, {}))
      .toEqual({ kind: "suspend", reason: "expired" });
  });

  it("ignores ACK-like bodies on non-200 responses", () => {
    for (const status of [401, 403, 409, 204]) {
      expect(resolveDeferredGpsAttempt(batch, { ...base, status }, ack))
        .toEqual({ kind: "suspend", reason: "http" });
    }
    expect(resolveDeferredGpsAttempt(batch, { ...base, status: 429, retryAfter: "5" }, ack))
      .toEqual({ kind: "retry", delayMs: 5000 });
    expect(resolveDeferredGpsAttempt(batch, { ...base, status: null }, ack))
      .toEqual({ kind: "retry", delayMs: 1000 });
  });
});
