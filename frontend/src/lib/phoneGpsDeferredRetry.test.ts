import { describe, expect, it } from "vitest";
import { decideDeferredGpsRetry, type DeferredRetryInput } from "./phoneGpsDeferredRetry";

const base: DeferredRetryInput = {
  status: null, attempts: 1, remainingMs: 120_000, contextValid: true,
  wallNowMs: Date.parse("Sun, 22 Nov 2026 10:00:00 GMT"),
};

describe("deferred GPS retry policy", () => {
  it("retries missing responses and transient errors with bounded exponential delay", () => {
    expect(decideDeferredGpsRetry(base)).toEqual({ kind: "retry", delayMs: 1000 });
    expect(decideDeferredGpsRetry({ ...base, status: 503, attempts: 4 }))
      .toEqual({ kind: "retry", delayMs: 8000 });
    expect(decideDeferredGpsRetry({ ...base, status: 500, attempts: 7 }))
      .toEqual({ kind: "retry", delayMs: 30_000 });
  });

  it("honors Retry-After as seconds or an HTTP date", () => {
    expect(decideDeferredGpsRetry({ ...base, status: 429, retryAfter: "60" }))
      .toEqual({ kind: "retry", delayMs: 60_000 });
    expect(decideDeferredGpsRetry({ ...base, status: 503, retryAfter: "Sun, 22 Nov 2026 10:01:00 GMT" }))
      .toEqual({ kind: "retry", delayMs: 60_000 });
    expect(decideDeferredGpsRetry({ ...base, status: 429, retryAfter: "-3" }))
      .toEqual({ kind: "retry", delayMs: 1000 });
  });

  it("suspends rather than violating the share deadline", () => {
    expect(decideDeferredGpsRetry({ ...base, remainingMs: 1000 }))
      .toEqual({ kind: "suspend", reason: "expired" });
    expect(decideDeferredGpsRetry({ ...base, status: 429, retryAfter: "120" }))
      .toEqual({ kind: "suspend", reason: "expired" });
    expect(decideDeferredGpsRetry({ ...base, status: 200, remainingMs: Number.NaN }))
      .toEqual({ kind: "suspend", reason: "expired" });
  });

  it("stops on revoked context even when a success arrives", () => {
    expect(decideDeferredGpsRetry({ ...base, status: 200, contextValid: false }))
      .toEqual({ kind: "suspend", reason: "context" });
  });

  it("never retries permanent or unexpected HTTP statuses", () => {
    for (const status of [201, 204, 301, 400, 401, 403, 404, 409, 413, 422, 600, NaN]) {
      expect(decideDeferredGpsRetry({ ...base, status }))
        .toEqual({ kind: "suspend", reason: "http" });
    }
  });

  it("stops after eight attempts or an invalid attempt counter", () => {
    for (const attempts of [0, -1, 1.5, 8, 100, NaN]) {
      expect(decideDeferredGpsRetry({ ...base, attempts }))
        .toEqual({ kind: "suspend", reason: "attempts" });
    }
  });

  it("hands a 200 to the existing full acknowledgement validator without confirming points", () => {
    expect(decideDeferredGpsRetry({ ...base, status: 200, attempts: 8 }))
      .toEqual({ kind: "acknowledge" });
  });
});
