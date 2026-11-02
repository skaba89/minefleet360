/**
 * Exports CSV (séparateur « ; », BOM UTF-8 pour Excel en français). Toute valeur commençant par un caractère
 * interprétable comme formule est neutralisée : un titre saisi par un utilisateur ne s'exécute jamais.
 */
export type CsvValue = string | number | boolean | null | undefined;

export const MAX_EXPORT_ROWS = 5000;

export function csvCell(value: CsvValue): string {
  if (value === null || value === undefined) return '""';
  const raw = typeof value === "boolean" ? (value ? "oui" : "non") : String(value);
  const safe = /^[\s]*[=+@\t\r-]/.test(raw) && !/^-?\d+([.,]\d+)?$/.test(raw.trim()) ? "'" + raw : raw;
  return '"' + safe.replaceAll('"', '""') + '"';
}

export function toCsv(header: string[], rows: CsvValue[][]): string {
  return "﻿" + [header, ...rows].map((row) => row.map(csvCell).join(";")).join("\r\n") + "\r\n";
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Toutes les pages d'une liste paginée, bornées à MAX_EXPORT_ROWS (signalé par `truncated`). */
export async function fetchAllPages<T>(
  fetchPage: (page: number, pageSize: number) => Promise<{ items: T[]; total: number }>,
): Promise<{ items: T[]; truncated: boolean }> {
  const pageSize = 200;
  const items: T[] = [];
  let total = Infinity;
  for (let page = 1; items.length < Math.min(total, MAX_EXPORT_ROWS); page += 1) {
    const result = await fetchPage(page, pageSize);
    total = result.total;
    items.push(...result.items);
    if (result.items.length < pageSize) break;
  }
  return { items: items.slice(0, MAX_EXPORT_ROWS), truncated: total > MAX_EXPORT_ROWS };
}

export function stamp(date: Date = new Date()): string {
  return date.toISOString().slice(0, 16).replace(/[-:T]/g, "");
}
