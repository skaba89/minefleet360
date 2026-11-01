import { decideRetry } from "./offline-retry";

export type SyncState = "pending" | "syncing" | "synchronized" | "rejected" | "reauthenticate";
export type SyncOutcome = { state: SyncState; attempts: number; retryAt: number | null; errorCode: string | null };

export function transitionAfterResponse(
  previousAttempts: number,
  status: number | null,
  nowMs: number,
  retryAfterSeconds?: number,
): SyncOutcome {
  if (!Number.isFinite(nowMs)) throw new RangeError("Horodatage invalide");
  const decision = decideRetry(status, previousAttempts, retryAfterSeconds);
  const attempts = previousAttempts + 1;
  switch (decision.action) {
    case "synchronized":
      return { state: "synchronized", attempts, retryAt: null, errorCode: null };
    case "reauthenticate":
      return { state: "reauthenticate", attempts, retryAt: null, errorCode: "SESSION_EXPIRED" };
    case "reject":
      return { state: "rejected", attempts, retryAt: null, errorCode: decision.reason };
    case "retry":
      return { state: "pending", attempts, retryAt: nowMs + decision.delayMs, errorCode: null };
  }
}

/** Garde-fou : une tâche terminale ou en cours ne peut pas repartir automatiquement. */
export function canStartSync(
  state: SyncState,
  retryAt: number | null,
  nowMs: number,
  authenticated: boolean,
  sameScope: boolean,
): boolean {
  return authenticated && sameScope && state === "pending" && (retryAt === null || retryAt <= nowMs);
}
