/** Tampon éphémère de relevés GPS : aucun stockage persistant, aucun rejeu après fermeture. */
export interface PhoneGpsSample {
  latitude: number;
  longitude: number;
  accuracy_m: number;
  speed_kmh: number | null;
  heading_deg: number | null;
  recorded_at: string;
}

const MAX_SAMPLES = 12;
const MAX_AGE_MS = 100_000; // marge sous la limite serveur de 2 minutes

export class PhoneGpsMemoryBuffer {
  private points: PhoneGpsSample[] = [];

  private prune(now: number): void {
    this.points = this.points.filter((point) => {
      const timestamp = Date.parse(point.recorded_at);
      return Number.isFinite(timestamp) && timestamp <= now + 5_000 && now - timestamp < MAX_AGE_MS;
    });
  }

  add(sample: PhoneGpsSample, now = Date.now()): void {
    this.prune(now);
    const recorded = Date.parse(sample.recorded_at);
    if (!Number.isFinite(recorded) || recorded > now + 5_000 || now - recorded >= MAX_AGE_MS) return;
    if (!Number.isFinite(sample.latitude) || Math.abs(sample.latitude) > 90
      || !Number.isFinite(sample.longitude) || Math.abs(sample.longitude) > 180
      || !Number.isFinite(sample.accuracy_m) || sample.accuracy_m < 0 || sample.accuracy_m > 10_000
      || (sample.speed_kmh !== null && (!Number.isFinite(sample.speed_kmh) || sample.speed_kmh < 0 || sample.speed_kmh > 250))
      || (sample.heading_deg !== null && (!Number.isFinite(sample.heading_deg) || sample.heading_deg < 0 || sample.heading_deg >= 360))) return;
    if (this.points.some((p) => p.recorded_at === sample.recorded_at)) return;
    this.points.push(sample);
    this.points.sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
    if (this.points.length > MAX_SAMPLES) this.points.splice(0, this.points.length - MAX_SAMPLES);
  }

  next(now = Date.now()): PhoneGpsSample | undefined {
    this.prune(now);
    return this.points[0];
  }

  confirm(recordedAt: string): void {
    this.points = this.points.filter((point) => point.recorded_at !== recordedAt);
  }

  count(now = Date.now()): number {
    this.prune(now);
    return this.points.length;
  }

  clear(): void {
    this.points = [];
  }
}
