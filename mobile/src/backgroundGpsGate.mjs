/**
 * Pure fail-closed safety gate for a future Android/iOS background GPS adapter.
 * No OS permissions, geolocation, HTTP, storage or native task is started here.
 * Native adapters must re-evaluate this gate before EACH GPS acquisition and upload.
 *
 * @typedef {{
 *   consent: boolean, authenticated: boolean, authorizedVehicle: boolean,
 *   foregroundPermission: boolean, backgroundPermission: boolean,
 *   shareActive: boolean, revoked: boolean, shareExpiresAtMs: number,
 *   nowMs: number, networkAvailable: boolean
 * }} BackgroundGpsContext
 *
 * @returns are descriptive decisions, NOT side effects. The native adapter must
 * cancel its OS location task and clear its encrypted queue on a 'stop' decision.
 */
export function decideBackgroundGps(context) {
  const validDeadline = Number.isSafeInteger(context.nowMs)
    && Number.isSafeInteger(context.shareExpiresAtMs)
    && context.nowMs >= 0
    && context.shareExpiresAtMs > context.nowMs;

  // Revocation and authorization are security boundaries, not recoverable
  // transient errors. No subsequent GPS reading or queue replay is permitted.
  if (!context.consent || !context.authenticated || !context.authorizedVehicle
      || !context.shareActive || context.revoked || !validDeadline) {
    return { action: "stop", purgeQueuedPoints: true };
  }
  if (!context.foregroundPermission || !context.backgroundPermission) {
    return { action: "stop", purgeQueuedPoints: true };
  }
  // A temporary loss of network is not permission to extend a lease or to
  // transmit unverified measurements. A native encrypted vault is required
  // before any offline sampling is enabled; no such vault is provided here.
  if (!context.networkAvailable) {
    return { action: "suspend", purgeQueuedPoints: false };
  }
  return { action: "allow", purgeQueuedPoints: false };
}
