import { gpsRetryDelayMs } from "./gpsRetry";

export const DEFERRED_MAX_ATTEMPTS = 8;

export type DeferredRetryDecision =
  | { kind: "acknowledge" }
  | { kind: "retry"; delayMs: number }
  | { kind: "suspend"; reason: "context" | "expired" | "attempts" | "http" };

export interface DeferredRetryInput {
  /** Null denotes a missing response, including an ambiguous network failure. */
  status: number | null;
  attempts: number;
  /** Remaining validity, measured against the monotonic share deadline. */
  remainingMs: number;
  contextValid: boolean;
  retryAfter?: string | null;
  /** Wall clock only for parsing the HTTP-date form of Retry-After. */
  wallNowMs: number;
}

function retryAfterMs(header: string | null | undefined, wallNowMs: number): number {
  const value = header?.trim();
  if (!value) return 0;
  if (/^\d+$/.test(value)) return Number(value) * 1000;
  // HTTP-date (IMF-fixdate); do not accept arbitrary locale/date formats.
  if (!/^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(value)) return 0;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && Number.isFinite(wallNowMs)
    ? Math.max(0, timestamp - wallNowMs)
    : 0;
}

/** Pure policy, not a scheduler. Never refresh a session or discard a queued point. */
export function decideDeferredGpsRetry(input: DeferredRetryInput): DeferredRetryDecision {
  if (!input.contextValid) return { kind: "suspend", reason: "context" };
  if (!Number.isFinite(input.remainingMs) || input.remainingMs <= 0) {
    return { kind: "suspend", reason: "expired" };
  }
  if (input.status === 200) return { kind: "acknowledge" }; // caller validates the entire ACK
  if (input.status !== null && input.status !== 429
    && !(Number.isInteger(input.status) && input.status >= 500 && input.status <= 599)) {
    return { kind: "suspend", reason: "http" };
  }
  if (!Number.isSafeInteger(input.attempts) || input.attempts < 1 || input.attempts >= DEFERRED_MAX_ATTEMPTS) {
    return { kind: "suspend", reason: "attempts" };
  }
  const delayMs = Math.max(gpsRetryDelayMs(input.attempts), retryAfterMs(input.retryAfter, input.wallNowMs));
  if (!Number.isFinite(delayMs) || delayMs >= input.remainingMs) {
    return { kind: "suspend", reason: "expired" };
  }
  return { kind: "retry", delayMs };
}
