import { expect, it } from "vitest";
import { PhoneGpsMemoryBuffer, type PhoneGpsSample } from "./phoneGpsMemoryBuffer";

const now = Date.parse("2026-11-05T07:00:00Z");
function sample(ageMs: number, lat = 9.5): PhoneGpsSample {
  return { latitude: lat, longitude: -13.7, accuracy_m: 12, speed_kmh: 42, heading_deg: 90,
    recorded_at: new Date(now - ageMs).toISOString() };
}

it("conserve seulement les relevés récents en mémoire, par ordre chronologique", () => {
  const queue = new PhoneGpsMemoryBuffer();
  queue.add(sample(20_000), now);
  queue.add(sample(30_000), now);
  queue.add(sample(20_000), now);
  queue.add(sample(120_000), now);
  expect(queue.count(now)).toBe(2);
  expect(queue.next(now)?.recorded_at).toBe(sample(30_000).recorded_at);
  queue.confirm(sample(30_000).recorded_at);
  expect(queue.next(now)?.recorded_at).toBe(sample(20_000).recorded_at);
});

it("borne la file à 12 points et purge les points devenus périmés", () => {
  const queue = new PhoneGpsMemoryBuffer();
  for (let i = 20; i >= 0; i--) queue.add(sample(i * 1_000), now);
  expect(queue.count(now)).toBe(12);
  expect(queue.next(now)?.recorded_at).toBe(sample(11_000).recorded_at);
  expect(queue.count(now + 120_000)).toBe(0);
});

it("refuse les coordonnées invalides et efface à l'arrêt", () => {
  const queue = new PhoneGpsMemoryBuffer();
  queue.add({ ...sample(0), latitude: 100 }, now);
  queue.add({ ...sample(0), longitude: Number.NaN }, now);
  queue.add({ ...sample(0), speed_kmh: 300 }, now);
  queue.add({ ...sample(0), heading_deg: Number.NaN }, now);
  expect(queue.count(now)).toBe(0);
  queue.add(sample(0), now);
  expect(queue.count(now)).toBe(1);
  queue.clear();
  expect(queue.count(now)).toBe(0);
});
