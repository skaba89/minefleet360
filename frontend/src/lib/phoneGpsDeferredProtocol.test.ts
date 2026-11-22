import { describe, expect, it } from "vitest";
import {
  buildDeferredGpsBatch,
  readDeferredGpsAcknowledgement,
  DEFERRED_MAX_BYTES,
  DEFERRED_MAX_POINTS,
  type DeferredGpsPoint,
} from "./phoneGpsDeferredProtocol";

function point(n: number): DeferredGpsPoint {
  return {
    client_point_id: "00000000-0000-4000-8000-" + String(n).padStart(12, "0"),
    recorded_at: "2026-01-01T12:00:00Z",
    latitude: 9.5,
    longitude: -13.7,
    accuracy_m: 10,
    speed_kmh: null,
    heading_deg: null,
  };
}

describe("deferred GPS wire protocol", () => {
  it("builds a bounded FIFO prefix with stable IDs and deterministic bytes", () => {
    const points = Array.from({ length: 101 }, (_, i) => point(i));
    const batch = buildDeferredGpsBatch(points)!;
    expect(batch.ids).toEqual(points.slice(0, DEFERRED_MAX_POINTS).map((p) => p.client_point_id));
    expect(JSON.parse(batch.body).points).toEqual(points.slice(0, DEFERRED_MAX_POINTS));
    expect(buildDeferredGpsBatch(points)).toEqual(batch);
    expect(new TextEncoder().encode(batch.body).byteLength).toBeLessThanOrEqual(DEFERRED_MAX_BYTES);
    expect(buildDeferredGpsBatch([])).toBeNull();
  });

  it("uses UTF-8 bytes rather than string length and never sends an empty batch", () => {
    const large = { ...point(1), recorded_at: "é".repeat(20_000) };
    const batch = buildDeferredGpsBatch([large, { ...large, client_point_id: point(2).client_point_id }])!;
    expect(batch.ids).toEqual([large.client_point_id]);
    expect(new TextEncoder().encode(batch.body).byteLength).toBeLessThanOrEqual(DEFERRED_MAX_BYTES);
    expect(() => buildDeferredGpsBatch([{ ...large, recorded_at: "é".repeat(DEFERRED_MAX_BYTES) }])).toThrow();
  });

  it("refuses invalid or repeated identities", () => {
    expect(() => buildDeferredGpsBatch([{ ...point(1), client_point_id: "invalid" }])).toThrow();
    expect(() => buildDeferredGpsBatch([point(1), point(1)])).toThrow();
  });

  it("confirms only accepted and duplicate points", () => {
    const batch = buildDeferredGpsBatch([point(1), point(2), point(3), point(4)])!;
    const [a, b, c, d] = batch.ids;
    expect(readDeferredGpsAcknowledgement(batch, {
      [a]: "accepted", [b]: "duplicate", [c]: "rejected", [d]: "conflict",
    })).toEqual({ confirmed: [a, b], rejected: [c], conflicts: [d] });
  });

  it("fails the entire acknowledgement on missing, unknown, or invalid entries", () => {
    const batch = buildDeferredGpsBatch([point(1), point(2)])!;
    const [a, b] = batch.ids;
    for (const response of [
      null, [], "accepted", {}, { [a]: "accepted" },
      { [a]: "accepted", [b]: "invalid" },
      { [a]: "accepted", [point(3).client_point_id]: "duplicate" },
      { [a]: "accepted", [b]: "duplicate", extra: "accepted" },
    ]) {
      expect(readDeferredGpsAcknowledgement(batch, response)).toBeNull();
    }
  });
});
