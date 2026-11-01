/** Décisions pures du futur moteur outbox : aucun stockage ni envoi implicite. */
export type RetryDecision =
  | { action: "retry"; delayMs: number }
  | { action: "reauthenticate" }
  | { action: "reject"; reason: "forbidden" | "conflict" | "invalid" | "client_error" }
  | { action: "synchronized" };

/** Une réponse inconnue (coupure/timeout) peut être rejouée seulement avec clé idempotente stable. */
export function decideRetry(
  status: number | null,
  attempts: number,
  retryAfterSeconds?: number,
): RetryDecision {
  if (!Number.isInteger(attempts) || attempts < 0) {
    throw new RangeError("attempts doit être un entier positif ou nul");
  }
  if (status !== null && (!Number.isInteger(status) || status < 100 || status > 599)) {
    throw new RangeError("statut HTTP invalide");
  }
  if (status !== null && status >= 200 && status < 300) return { action: "synchronized" };
  if (status === 401) return { action: "reauthenticate" };
  if (status === 403) return { action: "reject", reason: "forbidden" };
  if (status === 409) return { action: "reject", reason: "conflict" };
  if (status === 422) return { action: "reject", reason: "invalid" };
  if (status !== null && status >= 400 && status < 500 && status !== 429) {
    return { action: "reject", reason: "client_error" };
  }
  // Backoff plafonné à 60 s. Les erreurs réseau, 429 et 5xx sont transitoires.
  const backoff = Math.min(60_000, 1_000 * 2 ** Math.min(attempts, 6));
  const retryAfter = Number.isFinite(retryAfterSeconds)
    ? Math.max(0, Math.min(60_000, (retryAfterSeconds ?? 0) * 1_000))
    : 0;
  return { action: "retry", delayMs: Math.max(backoff, retryAfter) };
}
