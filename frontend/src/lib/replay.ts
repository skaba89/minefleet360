/**
 * Relecture d'un trajet mesuré. Règle : seules les positions **mesurées** font foi.
 * - Instant égal à une mesure (ou lecture en pause) : position mesurée.
 * - Entre deux mesures consécutives, hors trou de signal : position **interpolée**, signalée comme telle
 *   (glissement visuel, jamais enregistré ni présenté comme mesuré).
 * - Pendant un trou de signal (ou après la dernière mesure) : le marqueur reste sur la dernière mesure.
 */
export interface ReplayPoint {
  latitude: number;
  longitude: number;
  recorded_at: string;
  speed_kmh: number | null;
  heading_deg?: number | null;
}

export interface ReplayGap {
  start: string;
  end: string;
}

export interface ReplayFrame {
  latitude: number;
  longitude: number;
  /** Index de la dernière mesure au plus tard à l'instant demandé. */
  index: number;
  kind: "measured" | "interpolated" | "gap";
  recordedAt: string;
  speedKmh: number | null;
  headingDeg: number | null;
}

export function times(points: ReplayPoint[]): number[] {
  return points.map((p) => Date.parse(p.recorded_at));
}

/** Dernier index i tel que t[i] <= at (recherche dichotomique) ; -1 avant la première mesure. */
export function lastAtOrBefore(stamps: number[], at: number): number {
  let lo = 0;
  let hi = stamps.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (stamps[mid]! <= at) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

function inGap(gaps: ReplayGap[], from: number, to: number): boolean {
  return gaps.some((g) => Date.parse(g.start) < to && Date.parse(g.end) > from);
}

export function frameAt(points: ReplayPoint[], stamps: number[], gaps: ReplayGap[], at: number, interpolate: boolean): ReplayFrame | null {
  if (points.length === 0) return null;
  const i = Math.max(0, lastAtOrBefore(stamps, at));
  const p = points[i]!;
  const base = { index: i, recordedAt: p.recorded_at, speedKmh: p.speed_kmh, headingDeg: p.heading_deg ?? null };
  const next = points[i + 1];
  if (!next || stamps[i]! >= at) {
    return { ...base, latitude: p.latitude, longitude: p.longitude, kind: next || at <= stamps[i]! ? "measured" : "gap" };
  }
  if (inGap(gaps, stamps[i]!, stamps[i + 1]!)) {
    return { ...base, latitude: p.latitude, longitude: p.longitude, kind: "gap" };
  }
  if (!interpolate) {
    return { ...base, latitude: p.latitude, longitude: p.longitude, kind: "measured" };
  }
  const f = (at - stamps[i]!) / (stamps[i + 1]! - stamps[i]!);
  return {
    ...base,
    latitude: p.latitude + (next.latitude - p.latitude) * f,
    longitude: p.longitude + (next.longitude - p.longitude) * f,
    kind: "interpolated",
  };
}

/** Tronçons du tracé, coupés à chaque trou de signal (pas de ligne tracée là où rien n'a été mesuré). */
export function segments(points: ReplayPoint[], stamps: number[], gaps: ReplayGap[]): [number, number][][] {
  const out: [number, number][][] = [];
  let current: [number, number][] = [];
  points.forEach((p, i) => {
    if (i > 0 && inGap(gaps, stamps[i - 1]!, stamps[i]!)) {
      if (current.length > 1) out.push(current);
      current = [];
    }
    current.push([p.longitude, p.latitude]);
  });
  if (current.length > 1) out.push(current);
  return out;
}

/** Point cardinal du cap (8 directions). */
export function compass(heading: number): string {
  const names = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
  return names[Math.round((((heading % 360) + 360) % 360) / 45) % 8]!;
}
