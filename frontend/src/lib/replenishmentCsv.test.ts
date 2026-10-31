import { describe, expect, it } from "vitest";
import { replenishmentCsv } from "./replenishmentCsv";

describe("replenishment draft CSV", () => {
  it("exports only positive shortages without triggering procurement", () => {
    const csv = replenishmentCsv([
      { part: "Filtre", store: "Magasin A", available: 6, threshold: 15 },
      { part: "Huile", store: "Magasin A", available: 20, threshold: 10 },
    ]);
    expect(csv).toContain('"9";"BROUILLON À VALIDER"');
    expect(csv).not.toContain('"Huile"');
  });

  it("neutralizes spreadsheet formula injection and escapes quotes", () => {
    const csv = replenishmentCsv([
      { part: '=HYPERLINK("https://invalid.example")', store: 'A "B"', available: 0, threshold: 2 },
    ]);
    expect(csv).toContain("'=HYPERLINK");
    expect(csv).toContain('A ""B""');
  });
});
