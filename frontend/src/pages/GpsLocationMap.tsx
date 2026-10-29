import { useState } from "react";

import { GPS_SIGNAL_LABEL, gpsSignalState, type GpsSignalPoint } from "../lib/gpsSignal";
import { formatDateTime } from "../lib/time";

interface Location extends GpsSignalPoint {
  vehicle_id: string;
  latitude: number;
  longitude: number;
  received_at: string;
}

export function GpsLocationMap({ point, now, timezone }: { point: Location; now: number; timezone: string }) {
  const signal = gpsSignalState(point, now);
  const [enabledFor, setEnabledFor] = useState<string | null>(null);
  const safe = Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
    && Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180;
  const key = point.vehicle_id;
  const delta = 0.012;
  const bbox = [
    point.longitude - delta,
    point.latitude - delta,
    point.longitude + delta,
    point.latitude + delta,
  ].join(",");
  const query = new URLSearchParams({ bbox, layer: "mapnik", marker: `${point.latitude},${point.longitude}` });
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?${query.toString()}`;

  return (
    <section className="card gps-map-preview" aria-label="Carte de la dernière position">
      <h2>Dernière position connue</h2>
      <p className="muted small">
        Camion {point.vehicle_id.slice(0, 8)} · {GPS_SIGNAL_LABEL[signal]}
        <br />
        Relevé : {Number.isFinite(Date.parse(point.recorded_at)) ? formatDateTime(point.recorded_at, timezone) : "—"} ·
        Réception : {Number.isFinite(Date.parse(point.received_at)) ? formatDateTime(point.received_at, timezone) : "—"} ({timezone})
      </p>
      {!safe ? (
        <p role="alert">Coordonnées GPS invalides : carte indisponible.</p>
      ) : enabledFor === key ? (
        <>
          <iframe
            title={`Carte OpenStreetMap du camion ${point.vehicle_id.slice(0, 8)}`}
            src={mapUrl}
            className="gps-map-frame"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
          <p className="muted small">
            © Contributeurs OpenStreetMap. Cette carte montre une dernière position connue, pas une localisation garantie en direct.
          </p>
          <button type="button" onClick={() => setEnabledFor(null)}>Fermer la carte externe</button>
        </>
      ) : (
        <>
          <p>
            La carte est fournie par OpenStreetMap. Son ouverture transmettra la zone géographique
            du camion à ce service externe. À réserver aux données autorisées.
            L'autorisation couvre aussi les prochains relevés de ce véhicule tant que cette carte reste ouverte.
          </p>
          <button type="button" className="primary" onClick={() => setEnabledFor(key)}>
            Afficher cette position sur la carte
          </button>
        </>
      )}
    </section>
  );
}
