import { useEffect, useRef, useState } from "react";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import { createMap } from "../lib/maplibre";

/** Les saisies restent au format latitude, longitude. La carte ne remplace pas la validation de l'API. */
export function readPolygonDraft(text: string): [number, number][] {
  if (!text.trim()) return [];
  const result: [number, number][] = [];
  for (const line of text.split(/\r?\n/).filter((part) => part.trim())) {
    const fields = line.trim().split(/[;,\s]+/);
    if (fields.length !== 2) return [];
    const [latitude, longitude] = fields.map(Number);
    if (latitude === undefined || longitude === undefined ||
        !Number.isFinite(latitude) || !Number.isFinite(longitude) ||
        Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return [];
    result.push([longitude, latitude]);
  }
  return result;
}

function polygonData(points: [number, number][]) {
  return {
    type: "FeatureCollection" as const,
    features: points.length < 3 ? [] : [{
      type: "Feature" as const,
      properties: {},
      geometry: {
        type: "Polygon" as const,
        coordinates: [[...points, points[0]!]],
      },
    }],
  };
}

function lineData(points: [number, number][]) {
  return {
    type: "FeatureCollection" as const,
    features: points.length < 2 ? [] : [{
      type: "Feature" as const,
      properties: {},
      geometry: { type: "LineString" as const, coordinates: points },
    }],
  };
}

function formatted(points: [number, number][]): string {
  return points.map(([lon, lat]) => `${lat.toFixed(6)}, ${lon.toFixed(6)}`).join("\n");
}

/** Dessin progressif : chaque clic ajoute un sommet, sauvegarde uniquement via le formulaire parent. */
export function GeofenceDrawMap({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const element = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onChangeRef = useRef(onChange);
  const pointsRef = useRef<[number, number][]>([]);
  const [loaded, setLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const points = readPolygonDraft(value);

  onChangeRef.current = onChange;
  pointsRef.current = points;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!element.current) return;
      try {
        const { map } = await createMap(element.current);
        if (cancelled) {
          map.remove();
          return;
        }
        mapRef.current = map;
        map.on("load", () => {
          if (cancelled) return;
          map.addSource("geofence-fill", { type: "geojson", data: polygonData(pointsRef.current) });
          map.addSource("geofence-outline", { type: "geojson", data: lineData(pointsRef.current) });
          map.addLayer({
            id: "geofence-fill",
            type: "fill",
            source: "geofence-fill",
            paint: { "fill-color": "#1d8f7a", "fill-opacity": 0.23 },
          });
          map.addLayer({
            id: "geofence-outline",
            type: "line",
            source: "geofence-outline",
            paint: { "line-color": "#126a5a", "line-width": 3 },
          });
          setLoaded(true);
        });
        map.on("click", (event) => {
          const next: [number, number][] = [
            ...pointsRef.current,
            [event.lngLat.lng, event.lngLat.lat],
          ];
          onChangeRef.current(formatted(next));
        });
      } catch {
        if (!cancelled) setUnavailable(true);
      }
    })();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    (map.getSource("geofence-fill") as GeoJSONSource | undefined)?.setData(polygonData(points));
    (map.getSource("geofence-outline") as GeoJSONSource | undefined)?.setData(lineData(points));
  }, [value, loaded]);

  return (
    <section aria-label="Dessiner une zone sur la carte">
      <p className="muted small">
        Cliquez sur la carte pour placer au moins trois sommets. Vous pouvez aussi modifier
        les coordonnées dans le champ ci-dessous. Le dessin n'est enregistré qu'au clic sur « Enregistrer la zone ».
      </p>
      {unavailable ? (
        <p role="status">Carte indisponible (WebGL ou fond de carte) : la saisie des coordonnées reste disponible.</p>
      ) : (
        <div ref={element} aria-label="Carte interactive de dessin" style={{ width: "100%", height: 340, borderRadius: 8 }} />
      )}
      <div className="inline-form">
        <span aria-live="polite">{points.length} sommet(s) saisi(s)</span>
        <button type="button" disabled={points.length === 0} onClick={() => onChange(formatted(points.slice(0, -1)))}>
          Annuler le dernier sommet
        </button>
        <button type="button" disabled={points.length === 0} onClick={() => onChange("")}>
          Effacer le dessin
        </button>
      </div>
    </section>
  );
}
