import { describe, expect, it } from "vitest";

import { gpsSignalState, type GpsSignalPoint } from "./gpsSignal";

const NOW = Date.parse("2026-10-29T12:00:00Z");
const recent: GpsSignalPoint = {
  recorded_at: "2026-10-29T11:59:30Z",
  received_at: "2026-10-29T12:00:00Z",
  speed_kmh: 30,
};

describe("fraîcheur des relevés GPS", () => {
  it("ne transforme pas un relevé différé en mouvement actuel à la reconnexion", () => {
    expect(gpsSignalState({ ...recent, recorded_at: "2026-10-29T10:00:00Z" }, NOW)).toBe("offline");
  });

  it("fait vieillir le point même si aucun nouveau point n'arrive", () => {
    expect(gpsSignalState(recent, NOW)).toBe("moving");
    expect(gpsSignalState(recent, NOW + 120_001)).toBe("offline");
  });

  it.each(["recorded_at", "received_at"] as const)("refuse un %s invalide ou trop futur", (field) => {
    expect(gpsSignalState({ ...recent, [field]: "invalide" }, NOW)).toBe("offline");
    expect(gpsSignalState({ ...recent, [field]: "2026-10-29T12:02:01Z" }, NOW)).toBe("offline");
  });

  it("refuse un relevé postérieur à la réception au-delà de la tolérance", () => {
    expect(gpsSignalState({
      ...recent,
      recorded_at: "2026-10-29T12:02:00Z",
      received_at: "2026-10-29T11:59:59Z",
    }, NOW)).toBe("offline");
  });

  it("accepte deux minutes de dérive d'horloge et la borne de fraîcheur", () => {
    expect(gpsSignalState({ ...recent, recorded_at: "2026-10-29T12:02:00Z" }, NOW)).toBe("moving");
    expect(gpsSignalState({ ...recent, recorded_at: "2026-10-29T11:58:00Z" }, NOW)).toBe("moving");
    expect(gpsSignalState({ ...recent, recorded_at: "2026-10-29T11:57:59.999Z" }, NOW)).toBe("offline");
  });

  it("compare les instants même avec des décalages UTC différents", () => {
    expect(gpsSignalState({ ...recent, recorded_at: "2026-10-29T12:59:30+01:00" }, NOW)).toBe("moving");
  });

  it.each([undefined, null, Number.NaN, Number.POSITIVE_INFINITY, -1, 251])(
    "ne déduit pas un arrêt d'une vitesse absente ou invalide (%s)",
    (speed_kmh) => {
      expect(gpsSignalState({ ...recent, speed_kmh }, NOW)).toBe("unknown");
    },
  );

  it.each([0, 2])("reconnaît un arrêt avec une vitesse valide (%s)", (speed_kmh) => {
    expect(gpsSignalState({ ...recent, speed_kmh }, NOW)).toBe("stopped");
  });

  it("refuse une horloge locale invalide", () => {
    expect(gpsSignalState(recent, Number.NaN)).toBe("offline");
  });
});
