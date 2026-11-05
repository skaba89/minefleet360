import { expect, it } from "vitest";
import { gpsRetryDelayMs } from "./gpsRetry";

it("augmente la pause de reconnexion sans saturer le serveur", () => {
  expect([1, 2, 3, 4, 5, 6, 30].map(gpsRetryDelayMs))
    .toEqual([1000, 2000, 4000, 8000, 16000, 30000, 30000]);
});

it("garde une valeur sûre pour des comptes invalides", () => {
  expect(gpsRetryDelayMs(0)).toBe(1000);
  expect(gpsRetryDelayMs(-9)).toBe(1000);
  expect(gpsRetryDelayMs(Number.NaN)).toBe(1000);
});
