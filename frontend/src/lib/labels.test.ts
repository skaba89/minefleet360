import { describe, expect, it } from "vitest";

import { formatDuration, formatTonnes } from "./labels";

describe("formatTonnes", () => {
  it("affiche des tonnes à deux décimales à partir de kilogrammes entiers", () => {
    expect(formatTonnes(34_000).replace(/\s/g, " ")).toBe("34,00 t");
    expect(formatTonnes(1_234_567).replace(/\s/g, " ")).toBe("1 234,57 t");
  });

  it("affiche un tiret sans valeur", () => {
    expect(formatTonnes(null)).toBe("—");
    expect(formatTonnes(undefined)).toBe("—");
  });
});

describe("formatDuration", () => {
  it("affiche minutes puis heures", () => {
    expect(formatDuration(600)).toBe("10 min");
    expect(formatDuration(3_900)).toBe("1 h 05");
    expect(formatDuration(null)).toBe("—");
  });
});
