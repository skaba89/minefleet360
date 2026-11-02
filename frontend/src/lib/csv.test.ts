import { describe, expect, it } from "vitest";

import { csvCell, fetchAllPages, MAX_EXPORT_ROWS, toCsv } from "./csv";

describe("export CSV", () => {
  it("neutralise les formules sans altérer les nombres négatifs", () => {
    expect(csvCell("=HYPERLINK(\"http://x\")")).toBe('"\'=HYPERLINK(""http://x"")"');
    expect(csvCell("+33 1")).toBe('"\'+33 1"');
    expect(csvCell("@SUM(A1)")).toBe('"\'@SUM(A1)"');
    expect(csvCell("-12.5")).toBe('"-12.5"');
    expect(csvCell("- titre piégé")).toBe('"\'- titre piégé"');
    expect(csvCell(true)).toBe('"oui"');
    expect(csvCell(null)).toBe('""');
  });

  it("produit un fichier lisible par Excel en français", () => {
    const csv = toCsv(["A", "B"], [["x", 1]]);
    expect(csv.startsWith("﻿")).toBe(true);
    expect(csv).toBe('﻿"A";"B"\r\n"x";"1"\r\n');
  });

  it("parcourt toutes les pages et signale la troncature", async () => {
    const all = Array.from({ length: 450 }, (_, i) => i);
    const calls: number[] = [];
    const result = await fetchAllPages(async (page, size) => {
      calls.push(page);
      return { items: all.slice((page - 1) * size, page * size), total: all.length };
    });
    expect(result.items).toHaveLength(450);
    expect(result.truncated).toBe(false);
    expect(calls).toEqual([1, 2, 3]);

    const huge = await fetchAllPages(async (_page, size) => ({ items: Array(size).fill(0), total: 999_999 }));
    expect(huge.items).toHaveLength(MAX_EXPORT_ROWS);
    expect(huge.truncated).toBe(true);
  });
});
