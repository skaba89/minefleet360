import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { GpsSignalState } from "../lib/gpsSignal";
import { createMap, reducedMotion } from "../lib/maplibre";
import { compass } from "../lib/replay";

/** Engin à afficher : position **mesurée** (jamais estimée), état du signal et textes déjà formatés. */
export interface MapVehicle {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  state: GpsSignalState;
  stateLabel: string;
  speedText: string;
  recordedText: string;
  /** Cap **mesuré** par l'équipement (degrés, 0 = nord) ; null s'il n'est pas transmis. */
  headingDeg?: number | null;
}

export interface MapGeofence {
  id: string;
  name: string;
  coordinates: [number, number][];
}

const MOVE_MS = 800;
/** En dessous de ce zoom, les engins sont des points (étiquette au survol, au focus ou à la sélection). */
const LABEL_ZOOM = 11;

function validPosition(v: MapVehicle): boolean {
  return Number.isFinite(v.latitude) && Number.isFinite(v.longitude) && Math.abs(v.latitude) <= 90 && Math.abs(v.longitude) <= 180;
}

/**
 * Transition **visuelle** entre deux positions mesurées : le marqueur glisse de l'ancienne vers la nouvelle, puis
 * s'arrête exactement sur la mesure. Aucune position intermédiaire n'est affichée comme mesurée ni enregistrée.
 */
function glide(marker: Marker, to: [number, number]) {
  const from = marker.getLngLat();
  if (reducedMotion() || (from.lng === to[0] && from.lat === to[1])) {
    marker.setLngLat(to);
    return;
  }
  const start = performance.now();
  const step = (time: number) => {
    const t = Math.min(1, (time - start) / MOVE_MS);
    marker.setLngLat([from.lng + (to[0] - from.lng) * t, from.lat + (to[1] - from.lat) * t]);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function showHeading(v: MapVehicle): v is MapVehicle & { headingDeg: number } {
  return v.state === "moving" && v.headingDeg != null && Number.isFinite(v.headingDeg);
}

function markerTitle(v: MapVehicle): string {
  const heading = showHeading(v) ? ` · cap ${Math.round(v.headingDeg)}° (${compass(v.headingDeg)})` : "";
  return `${v.label} · ${v.stateLabel} · ${v.speedText}${heading} · position mesurée ${v.recordedText}`;
}

function geofenceData(geofences: MapGeofence[]) {
  return {
    type: "FeatureCollection" as const,
    features: geofences.map((g) => ({
      type: "Feature" as const,
      properties: { name: g.name },
      geometry: { type: "Polygon" as const, coordinates: [g.coordinates] },
    })),
  };
}

export function FleetMap({
  vehicles,
  geofences = [],
  selectedId,
  onSelect,
}: {
  vehicles: MapVehicle[];
  geofences?: MapGeofence[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; button: HTMLButtonElement }>());
  const fitted = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const [ready, setReady] = useState(false);
  const [withBasemap, setWithBasemap] = useState<boolean | null>(null);
  const [failure, setFailure] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!container.current) return;
      try {
        const { map, withBasemap: available } = await createMap(container.current);
        if (cancelled) {
          map.remove();
          return;
        }
        setWithBasemap(available);
        const toggleLabels = () => container.current?.classList.toggle("fleet-map--labels", map.getZoom() >= LABEL_ZOOM);
        map.on("zoomend", toggleLabels);
        map.on("load", () => {
          toggleLabels();
          map.addSource("geofences", { type: "geojson", data: geofenceData([]) });
          map.addLayer({ id: "geofences-fill", type: "fill", source: "geofences", paint: { "fill-color": "#2f6fb0", "fill-opacity": 0.08 } });
          map.addLayer({ id: "geofences-line", type: "line", source: "geofences", paint: { "line-color": "#2f6fb0", "line-width": 1.5 } });
          if (!cancelled) setReady(true);
        });
        mapRef.current = map;
      } catch {
        // WebGL indisponible (vieil appareil, navigateur restreint) : la liste des engins reste utilisable.
        if (!cancelled) setFailure(true);
      }
    })();
    return () => {
      cancelled = true;
      for (const { marker } of markers.current.values()) marker.remove();
      markers.current.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const shown = vehicles.filter(validPosition);
    const seen = new Set<string>();
    for (const v of shown) {
      seen.add(v.id);
      const target: [number, number] = [v.longitude, v.latitude];
      let entry = markers.current.get(v.id);
      if (!entry) {
        const button = document.createElement("button");
        button.type = "button";
        button.addEventListener("click", () => onSelectRef.current(v.id));
        const marker = new maplibregl.Marker({ element: button, anchor: "bottom" }).setLngLat(target).addTo(map);
        entry = { marker, button };
        markers.current.set(v.id, entry);
      } else {
        glide(entry.marker, target);
      }
      entry.button.className = `fleet-marker fleet-marker--${v.state}${v.id === selectedId ? " fleet-marker--selected" : ""}`;
      const text = document.createElement("span");
      text.className = "fleet-marker-label";
      text.textContent = v.label;
      if (showHeading(v)) {
        // Flèche orientée selon le cap mesuré (jamais affichée si l'équipement ne l'envoie pas).
        const arrow = document.createElement("span");
        arrow.className = "fleet-marker-arrow";
        arrow.setAttribute("aria-hidden", "true");
        arrow.style.transform = `rotate(${v.headingDeg}deg)`;
        entry.button.replaceChildren(arrow, text);
      } else {
        entry.button.replaceChildren(text);
      }
      entry.button.title = markerTitle(v);
      entry.button.setAttribute("aria-label", markerTitle(v));
      entry.button.setAttribute("aria-pressed", String(v.id === selectedId));
    }
    for (const [id, entry] of markers.current) {
      if (!seen.has(id)) {
        entry.marker.remove();
        markers.current.delete(id);
      }
    }
    if (!fitted.current && shown.length > 0) {
      fitted.current = true;
      const bounds = new maplibregl.LngLatBounds();
      for (const v of shown) bounds.extend([v.longitude, v.latitude]);
      map.fitBounds(bounds, { padding: 60, maxZoom: 14, duration: 0 });
    }
  }, [vehicles, selectedId, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("geofences") as GeoJSONSource | undefined)?.setData(geofenceData(geofences));
  }, [geofences, ready]);

  useEffect(() => {
    const map = mapRef.current;
    const target = vehicles.find((v) => v.id === selectedId && validPosition(v));
    if (!map || !ready || !target) return;
    map.easeTo({ center: [target.longitude, target.latitude], zoom: Math.max(map.getZoom(), 13), duration: reducedMotion() ? 0 : 600 });
    // Recentrer seulement au changement de sélection, pas à chaque nouvelle position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, ready]);

  return (
    <section className="card fleet-map" aria-label="Carte des engins">
      {failure ? (
        <p role="status">Carte indisponible sur cet appareil (WebGL). La liste des engins reste à jour.</p>
      ) : (
        <div ref={container} className="fleet-map-canvas" data-testid="fleet-map" />
      )}
      {withBasemap === false && !failure && (
        <p className="muted small">
          Fond de carte non installé sur ce serveur : positions et zones affichées sur un fond neutre.
        </p>
      )}
    </section>
  );
}
