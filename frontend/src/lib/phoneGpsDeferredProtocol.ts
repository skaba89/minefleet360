import type { PhoneGpsSample } from "./phoneGpsMemoryBuffer";

/** Pure wire protocol: no geolocation, network, storage or automatic replay. */
export interface DeferredGpsPoint extends PhoneGpsSample {
  client_point_id: string;
}

export const DEFERRED_MAX_POINTS = 100;
export const DEFERRED_MAX_BYTES = 64 * 1024;

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export interface DeferredGpsBatch {
  readonly ids: readonly string[];
  readonly body: string;
}

/** Serialize a FIFO prefix. IDs belong to samples and must survive any retry unchanged. */
export function buildDeferredGpsBatch(points: readonly DeferredGpsPoint[]): DeferredGpsBatch | null {
  if (points.length === 0) return null;
  const ids: string[] = [];
  const entries: string[] = [];
  const seen = new Set<string>();
  const encoder = new TextEncoder();
  let bytes = encoder.encode('{"points":[]}').byteLength;
  for (const point of points.slice(0, DEFERRED_MAX_POINTS)) {
    const id = point.client_point_id;
    if (!UUID_V4.test(id) || seen.has(id)) throw new Error("Invalid deferred point identity");
    const entry = JSON.stringify({
      client_point_id: id,
      recorded_at: point.recorded_at,
      latitude: point.latitude,
      longitude: point.longitude,
      accuracy_m: point.accuracy_m,
      speed_kmh: point.speed_kmh,
      heading_deg: point.heading_deg,
    });
    const entryBytes = encoder.encode(entry).byteLength + (entries.length ? 1 : 0);
    if (bytes + entryBytes > DEFERRED_MAX_BYTES) {
      if (!entries.length) throw new Error("Deferred point exceeds batch budget");
      break;
    }
    bytes += entryBytes;
    ids.push(id);
    entries.push(entry);
    seen.add(id);
  }
  return { ids, body: '{"points":[' + entries.join(",") + "]}" };
}

export interface DeferredGpsAcknowledgement {
  confirmed: string[];
  rejected: string[];
  conflicts: string[];
}

/** Fail closed: only a complete, exact acknowledgement can confirm any queued point. */
export function readDeferredGpsAcknowledgement(
  batch: DeferredGpsBatch,
  response: unknown,
): DeferredGpsAcknowledgement | null {
  if (!response || typeof response !== "object" || Array.isArray(response)) return null;
  const expected = new Set(batch.ids);
  if (!expected.size || expected.size !== batch.ids.length) return null;
  const entries = Object.entries(response);
  if (entries.length !== expected.size) return null;
  const result: DeferredGpsAcknowledgement = { confirmed: [], rejected: [], conflicts: [] };
  for (const [id, status] of entries) {
    if (!expected.delete(id)) return null;
    switch (status) {
      case "accepted":
      case "duplicate":
        result.confirmed.push(id);
        break;
      case "rejected":
        result.rejected.push(id);
        break;
      case "conflict":
        result.conflicts.push(id);
        break;
      default:
        return null;
    }
  }
  return expected.size === 0 ? result : null;
}
