import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, offsetMs, utcToZonedInput, zonedInputToUtc } from "./time";

// D-23 : Conakry est à UTC+0, un bug de fuseau y serait invisible ; on teste aussi UTC+1 et un fuseau à DST.
describe("fuseaux de site", () => {
  it("convertit une saisie à Lagos (UTC+1) en UTC", () => {
    expect(zonedInputToUtc("2026-10-27T08:00", "Africa/Lagos").toISOString()).toBe("2026-10-27T07:00:00.000Z");
    expect(zonedInputToUtc("2026-10-27T08:00", "Africa/Conakry").toISOString()).toBe("2026-10-27T08:00:00.000Z");
  });

  it("gère le changement d'heure (Paris, 29/03/2026)", () => {
    expect(zonedInputToUtc("2026-03-29T01:30", "Europe/Paris").toISOString()).toBe("2026-03-29T00:30:00.000Z");
    expect(zonedInputToUtc("2026-03-29T04:00", "Europe/Paris").toISOString()).toBe("2026-03-29T02:00:00.000Z");
  });

  it("fait l'aller-retour saisie ↔ instant", () => {
    const instant = new Date("2026-12-31T23:30:00Z");
    expect(utcToZonedInput(instant, "Africa/Lagos")).toBe("2027-01-01T00:30");
    expect(zonedInputToUtc(utcToZonedInput(instant, "Africa/Lagos"), "Africa/Lagos")).toEqual(instant);
    expect(offsetMs(instant, "Africa/Lagos")).toBe(3_600_000);
  });

  it("affiche en français au fuseau du site", () => {
    expect(formatDateTime("2026-10-27T23:30:00Z", "Africa/Lagos")).toBe("28/10/2026 00:30");
    expect(formatDateTime(null, "Africa/Lagos")).toBe("—");
    expect(formatDate("2030-01-05")).toBe("05/01/2030");
  });

  it("refuse une saisie mal formée", () => {
    expect(() => zonedInputToUtc("27/10/2026 08:00", "Africa/Conakry")).toThrow();
  });
});
