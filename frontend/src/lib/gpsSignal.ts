/** Freshness uses the measurement time as well as transport receipt time. */
export interface GpsSignalPoint {
  source_active?: boolean;
  recorded_at: string;
  received_at: string;
  speed_kmh?: number | null;
}

export type GpsSignalState = "moving" | "stopped" | "offline" | "unknown";

export const GPS_SIGNAL_LABEL: Record<GpsSignalState, string> = {
  moving: "En mouvement",
  stopped: "À l'arrêt",
  offline: "Signal ancien ou invalide",
  unknown: "Mouvement inconnu",
};

const FRESHNESS_MS = 120_000;
const CLOCK_SKEW_MS = 120_000;

export function gpsSignalState(point: GpsSignalPoint, now: number): GpsSignalState {
  const recorded = Date.parse(point.recorded_at);
  const received = Date.parse(point.received_at);
  if (
    point.source_active === false ||
    !Number.isFinite(now) ||
    !Number.isFinite(recorded) ||
    !Number.isFinite(received) ||
    now - recorded > FRESHNESS_MS ||
    now - received > FRESHNESS_MS ||
    recorded > now + CLOCK_SKEW_MS ||
    received > now + CLOCK_SKEW_MS ||
    recorded > received + CLOCK_SKEW_MS
  ) {
    return "offline";
  }

  const speed = point.speed_kmh;
  if (speed == null || !Number.isFinite(speed) || speed < 0 || speed > 250) {
    return "unknown";
  }
  return speed > 2 ? "moving" : "stopped";
}
