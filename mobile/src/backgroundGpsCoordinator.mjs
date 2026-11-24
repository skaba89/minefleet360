import { decideBackgroundGps } from "./backgroundGpsGate.mjs";

/**
 * Lifecycle coordinator for a future native Android/iOS GPS task.
 * No GPS sensor is started without an explicitly supplied native adapter.
 * Every transition is serialized so "stop" cannot race with a pending "start".
 *
 * @param {{
 *   startNative: () => Promise<void>,
 *   stopNative: () => Promise<void>,
 *   purgeQueuedPoints: () => Promise<void>
 * }} native
 */
export function createBackgroundGpsCoordinator(native) {
  if (typeof native?.startNative !== "function"
    || typeof native.stopNative !== "function"
    || typeof native.purgeQueuedPoints !== "function") {
    throw new TypeError("Explicit native task adapter and queue purge are required");
  }

  let state = "stopped";
  let sequence = Promise.resolve();
  const schedule = (operation) => {
    const result = sequence.then(operation);
    sequence = result.catch(() => undefined);
    return result;
  };

  const transition = async (context) => {
    const decision = decideBackgroundGps(context);
    if (decision.action === "allow") {
      if (state !== "running") {
        // Do not silently become 'running' when native startup fails.
        await native.startNative();
        state = "running";
      }
      return { state, decision };
    }
    if (state === "running") {
      // A native stop failure must prevent misleading 'stopped' status.
      await native.stopNative();
    }
    state = decision.action === "stop" ? "stopped" : "suspended";
    if (decision.purgeQueuedPoints) {
      await native.purgeQueuedPoints();
    }
    return { state, decision };
  };

  return {
    status: () => state,
    /** Re-check fresh permissions, lease and server authorization every time. */
    reconcile: (context) => schedule(() => transition(context)),
    /** Explicit user stop: always stop native work and erase the local queue. */
    stop: () => schedule(async () => {
      // Idempotent native stop is an adapter requirement.
      await native.stopNative();
      state = "stopped";
      await native.purgeQueuedPoints();
      return { state };
    }),
  };
}
