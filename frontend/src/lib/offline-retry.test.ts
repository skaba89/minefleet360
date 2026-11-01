import { describe, expect, it } from "vitest";

import { decideRetry } from "./offline-retry";

describe("politique de rejeu des opérations terrain", () => {
  it("acquitte uniquement les succès HTTP", () => {
    expect(decideRetry(201, 0)).toEqual({ action: "synchronized" });
    expect(decideRetry(204, 0)).toEqual({ action: "synchronized" });
  });

  it("suspend après expiration de session", () => {
    expect(decideRetry(401, 0)).toEqual({ action: "reauthenticate" });
  });

  it("bloque les refus, conflits et erreurs de validation", () => {
    expect(decideRetry(403, 0)).toEqual({ action: "reject", reason: "forbidden" });
    expect(decideRetry(409, 0)).toEqual({ action: "reject", reason: "conflict" });
    expect(decideRetry(422, 0)).toEqual({ action: "reject", reason: "invalid" });
    expect(decideRetry(404, 0)).toEqual({ action: "reject", reason: "client_error" });
  });

  it("réessaie seulement les pannes transitoires avec temporisation bornée", () => {
    expect(decideRetry(null, 0)).toEqual({ action: "retry", delayMs: 1000 });
    expect(decideRetry(500, 2)).toEqual({ action: "retry", delayMs: 4000 });
    expect(decideRetry(429, 0, 15)).toEqual({ action: "retry", delayMs: 15000 });
    expect(decideRetry(503, 20)).toEqual({ action: "retry", delayMs: 60000 });
  });

  it("refuse les compteurs et statuts non valides", () => {
    expect(() => decideRetry(null, -1)).toThrow(RangeError);
    expect(() => decideRetry(700, 0)).toThrow(RangeError);
  });
});
