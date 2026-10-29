import { expect, it } from "vitest";
import { gpsSignalState } from "./gpsSignal";

it("ne présente jamais comme actif un partage arrêté même avec un point récent", () => {
  const now = Date.now();
  expect(gpsSignalState({ source_active: false, recorded_at: new Date(now).toISOString(), received_at: new Date(now).toISOString(), speed_kmh: 30 }, now)).toBe("offline");
});
