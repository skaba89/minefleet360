import { describe, expect, it } from "vitest";

import { compass, frameAt, lastAtOrBefore, segments, times, type ReplayPoint } from "./replay";

const p = (minute: number, lat: number, lon: number, extra: Partial<ReplayPoint> = {}): ReplayPoint => ({
  latitude: lat, longitude: lon, recorded_at: new Date(Date.UTC(2026, 10, 4, 8, minute)).toISOString(), speed_kmh: 30, ...extra,
});
const at = (minute: number, seconds = 0) => Date.UTC(2026, 10, 4, 8, minute, seconds);
const points = [p(0, 10, -12, { heading_deg: 90 }), p(1, 10, -11.99), p(2, 10, -11.98), p(10, 10.1, -11.9)];
const stamps = times(points);
const gaps = [{ start: points[2]!.recorded_at, end: points[3]!.recorded_at }];

describe("relecture d'un trajet mesuré", () => {
  it("trouve la dernière mesure au plus tard à l'instant", () => {
    expect(lastAtOrBefore(stamps, at(0) - 1)).toBe(-1);
    expect(lastAtOrBefore(stamps, at(1))).toBe(1);
    expect(lastAtOrBefore(stamps, at(5))).toBe(2);
    expect(lastAtOrBefore(stamps, at(30))).toBe(3);
  });

  it("position mesurée sur une mesure, interpolée et signalée entre deux mesures", () => {
    expect(frameAt(points, stamps, gaps, at(1), true)).toMatchObject({ kind: "measured", longitude: -11.99, index: 1 });
    const half = frameAt(points, stamps, gaps, at(0, 30), true)!;
    expect(half.kind).toBe("interpolated");
    expect(half.longitude).toBeCloseTo(-11.995, 6);
    expect(half.recordedAt).toBe(points[0]!.recorded_at); // l'heure affichée reste celle de la dernière mesure
    expect(half.headingDeg).toBe(90);
  });

  it("n'interpole jamais à travers un trou de signal ni sans lecture en cours", () => {
    expect(frameAt(points, stamps, gaps, at(5), true)).toMatchObject({ kind: "gap", longitude: -11.98 });
    expect(frameAt(points, stamps, gaps, at(0, 30), false)).toMatchObject({ kind: "measured", longitude: -12 });
    expect(frameAt(points, stamps, gaps, at(30), true)).toMatchObject({ kind: "gap", latitude: 10.1 });
    expect(frameAt([], [], [], at(0), true)).toBeNull();
  });

  it("coupe le tracé aux trous de signal", () => {
    expect(segments(points, stamps, gaps)).toEqual([[[-12, 10], [-11.99, 10], [-11.98, 10]]]);
    expect(segments(points, stamps, [])).toHaveLength(1);
  });

  it("nomme le cap en 8 directions", () => {
    expect([0, 44, 90, 180, 225, 359, 360].map(compass)).toEqual(["N", "NE", "E", "S", "SO", "N", "N"]);
  });
});
