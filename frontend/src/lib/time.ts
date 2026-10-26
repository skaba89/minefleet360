// Dates : stockage et échanges en UTC, affichage et saisie au fuseau du site (D-23).
// Sans bibliothèque : Intl donne le décalage d'un fuseau à un instant donné.

const PARTS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
};

function wallClock(instant: Date, timeZone: string): Record<string, number> {
  const parts = new Intl.DateTimeFormat("en-US", { ...PARTS, timeZone }).formatToParts(instant);
  const out: Record<string, number> = {};
  for (const part of parts) if (part.type !== "literal") out[part.type] = Number(part.value);
  return out;
}

/** Décalage (ms) du fuseau par rapport à UTC à l'instant donné. */
export function offsetMs(instant: Date, timeZone: string): number {
  const w = wallClock(instant, timeZone);
  const asUtc = Date.UTC(w.year!, w.month! - 1, w.day!, w.hour!, w.minute!, w.second!);
  return asUtc - Math.floor(instant.getTime() / 1000) * 1000;
}

/** "2026-10-27T08:00" saisi au fuseau `timeZone` → instant UTC. */
export function zonedInputToUtc(local: string, timeZone: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(local);
  if (!match) throw new Error("Format de date invalide");
  const [, y, mo, d, h, mi] = match.map(Number) as [number, number, number, number, number, number];
  const naive = Date.UTC(y, mo - 1, d, h, mi);
  let utc = naive - offsetMs(new Date(naive), timeZone);
  const corrected = naive - offsetMs(new Date(utc), timeZone); // changement d'heure entre les deux
  if (corrected !== utc) utc = corrected;
  return new Date(utc);
}

/** Instant → valeur d'un champ `datetime-local` au fuseau `timeZone`. */
export function utcToZonedInput(instant: Date, timeZone: string): string {
  const w = wallClock(instant, timeZone);
  const pad = (n: number | undefined) => String(n).padStart(2, "0");
  return `${w.year}-${pad(w.month)}-${pad(w.day)}T${pad(w.hour)}:${pad(w.minute)}`;
}

/** Affichage français JJ/MM/AAAA HH:MM au fuseau du site. */
export function formatDateTime(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** Date calendaire "2030-01-01" → "01/01/2030" (sans conversion de fuseau). */
export function formatDate(day: string | null | undefined): string {
  if (!day) return "—";
  const [y, m, d] = day.split("-");
  return `${d}/${m}/${y}`;
}
