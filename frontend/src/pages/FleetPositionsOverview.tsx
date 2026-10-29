import { useMemo } from "react";

import { GPS_SIGNAL_LABEL, gpsSignalState, type GpsSignalPoint } from "../lib/gpsSignal";

export interface FleetMapPoint extends GpsSignalPoint {
  vehicle_id: string;
  latitude: number;
  longitude: number;
  received_at: string;
}

interface Props {
  points: FleetMapPoint[];
  selectedId: string | null;
  onSelect: (vehicleId: string) => void;
  now: number;
}

export function FleetPositionsOverview({ points, selectedId, onSelect, now }: Props) {
  const valid = useMemo(
    () =>
      points.filter(
        (point) =>
          Number.isFinite(point.latitude) &&
          Number.isFinite(point.longitude) &&
          Math.abs(point.latitude) <= 90 &&
          Math.abs(point.longitude) <= 180,
      ),
    [points],
  );
  if (valid.length === 0) {
    return <p className="muted">Aucune coordonnée disponible pour la vue d'ensemble.</p>;
  }

  const latitudes = valid.map((point) => point.latitude);
  const longitudes = valid.map((point) => point.longitude);
  const latMin = Math.min(...latitudes);
  const latMax = Math.max(...latitudes);
  const lonMin = Math.min(...longitudes);
  const lonMax = Math.max(...longitudes);
  const latSpan = Math.max(latMax - latMin, 0.005);
  const lonSpan = Math.max(lonMax - lonMin, 0.005);
  const project = (point: FleetMapPoint) => ({
    x: 8 + ((point.longitude - (lonMin + lonMax) / 2) / lonSpan + 0.5) * 84,
    y: 92 - ((point.latitude - (latMin + latMax) / 2) / latSpan + 0.5) * 84,
  });

  return (
    <section className="card fleet-positions-overview" aria-label="Vue GPS multi-camions">
      <h2>Vue d'ensemble des positions</h2>
      <p className="muted small">
        Schéma géographique relatif · sans fond cartographique ni envoi de données à un tiers.
        Sélectionnez un point pour consulter le camion.
      </p>
      <div className="fleet-positions-plot" role="group" aria-label="Camions géolocalisés">
        {valid.map((point) => {
          const { x, y } = project(point);
          const state = GPS_SIGNAL_LABEL[gpsSignalState(point, now)];
          return (
            <button
              key={point.vehicle_id}
              type="button"
              className={`fleet-position-dot${selectedId === point.vehicle_id ? " is-selected" : ""}`}
              style={{ left: `${x}%`, top: `${y}%` }}
              title={`Camion ${point.vehicle_id.slice(0, 8)} : ${point.latitude.toFixed(5)}, ${point.longitude.toFixed(5)} · ${state}`}
              aria-label={`Sélectionner le camion ${point.vehicle_id.slice(0, 8)} · ${state}`}
              aria-pressed={selectedId === point.vehicle_id}
              onClick={() => onSelect(point.vehicle_id)}
            >
              <span aria-hidden="true" />
            </button>
          );
        })}
      </div>
      <p className="muted small">
        {valid.length} camion(s) affiché(s). La position des points est relative aux limites
        du groupe ; les distances à l'écran ne constituent pas des distances routières.
      </p>
    </section>
  );
}
