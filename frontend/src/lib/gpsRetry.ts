/** Reconnexion GPS bornée : pas de rafale de requêtes quand le réseau est faible. */
export function gpsRetryDelayMs(failures: number): number {
  const attempt = Math.max(1, Math.min(6, Math.floor(Number.isFinite(failures) ? failures : 1)));
  return Math.min(30_000, 1_000 * 2 ** (attempt - 1));
}
