/** Export a review-only procurement draft. Never interpret names as spreadsheet formulas. */
export interface ReplenishmentLine {
  part: string;
  store: string;
  available: number;
  threshold: number;
}
function cell(value: string | number): string {
  const raw = String(value);
  const safe = /^[\s]*[=+@-\t\r]/.test(raw) ? "'" + raw : raw;
  return '"' + safe.replaceAll('"', '""') + '"';
}
export function replenishmentCsv(lines: ReplenishmentLine[]): string {
  const rows = [["Pièce", "Magasin", "Disponible", "Seuil", "Quantité indicative", "Statut"]];
  for (const line of lines) {
    const quantity = Math.max(0, line.threshold - line.available);
    if (quantity <= 0) continue;
    rows.push([
      line.part, line.store, String(line.available), String(line.threshold),
      String(quantity), "BROUILLON À VALIDER",
    ]);
  }
  return "\uFEFF" + rows.map((row) => row.map(cell).join(";")).join("\r\n") + "\r\n";
}
