import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import { createMap } from "../lib/maplibre";

export interface GeofenceMapZone {
  site_geofence_id: string;
  name: string;
  kind: string;
  coordinates: [number, number][];
}

/** The backend returns closed [longitude, latitude] rings. Never mutate server data. */
export function zonesGeoJSON(zones: GeofenceMapZone[]) {
  return {
    type: "FeatureCollection" as const,
    features: zones.filter((zone) => zone.coordinates.length >= 4).map((zone) => ({
      type: "Feature" as const,
      properties: {
        id: zone.site_geofence_id,
        name: zone.name,
        kind: zone.kind,
      },
      geometry: {
        type: "Polygon" as const,
        coordinates: [zone.coordinates],
      },
    })),
  };
}

/** Read-only overview: the server already filters zones by tenant, site and RBAC. */
export function GeofenceOverviewMap({ zones }: { zones: GeofenceMapZone[] }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const zonesRef = useRef(zones);
  const [ready, setReady] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  zonesRef.current = zones;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!container.current) return;
      try {
        const { map } = await createMap(container.current);
        if (cancelled) {
          map.remove();
          return;
        }
        mapRef.current = map;
        map.on("load", () => {
          if (cancelled) return;
          map.addSource("visible-geofences", { type: "geojson", data: zonesGeoJSON(zonesRef.current) });
          map.addLayer({
            id: "visible-geofences-fill",
            type: "fill",
            source: "visible-geofences",
            paint: {
              "fill-color": ["match", ["get", "kind"], "RESTRICTED", "#c14444", "SITE_BOUNDARY", "#2d70ba", "#16856e"],
              "fill-opacity": 0.22,
            },
          });
          map.addLayer({
            id: "visible-geofences-outline",
            type: "line",
            source: "visible-geofences",
            paint: { "line-color": "#285a59", "line-width": 2 },
          });
          map.on("click", "visible-geofences-fill", (event) => {
            const feature = event.features?.[0];
            if (!feature) return;
            const name = String(feature.properties?.name ?? "");
            const kind = String(feature.properties?.kind ?? "");
            new maplibregl.Popup().setLngLat(event.lngLat).setText(`${name} — ${kind}`).addTo(map);
          });
          setReady(true);
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
    if (!ready || !map) return;
    (map.getSource("visible-geofences") as GeoJSONSource | undefined)?.setData(zonesGeoJSON(zones));
    const bounds = new maplibregl.LngLatBounds();
    for (const zone of zones) {
      for (const point of zone.coordinates) bounds.extend(point);
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
  }, [zones, ready]);

  return (
    <section aria-label="Carte des zones GPS">
      <h2>Carte des zones actives</h2>
      <p className="muted small">Zones interdites en rouge, limites de site en bleu et autres zones en vert. Sélectionnez une zone sur la carte pour voir son nom.</p>
      {unavailable ? (
        <p role="status">Carte indisponible sur cet appareil ; la liste des zones reste accessible.</p>
      ) : (
        <div ref={container} aria-label="Carte des géofences existantes" style={{ width: "100%", height: 360, borderRadius: 8 }} />
      )}
    </section>
  );
}
