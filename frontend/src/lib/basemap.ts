import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

/**
 * Fond de carte auto-hébergé (décision du 4 novembre 2026, docs/GPS_LIVE_MAP.md) : extrait OpenStreetMap de la
 * Guinée au format PMTiles, servi par le conteneur web sous /basemap/. Aucune position consultée n'est envoyée à un
 * tiers. Sans ce fichier (développement, CI), la carte reste utilisable sur un fond neutre.
 */
export const BASEMAP_PATH = "/basemap/guinee.pmtiles";
export const OSM_ATTRIBUTION = "© contributeurs OpenStreetMap (ODbL)";

/** Le fichier est présent si le serveur le sert (et non la page de l'application). */
export async function basemapAvailable(fetcher: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetcher(BASEMAP_PATH, { method: "HEAD" });
    const type = response.headers.get("content-type") ?? "";
    return response.ok && !type.includes("text/html");
  } catch {
    return false;
  }
}

/**
 * Style MapLibre. Les couches de texte du fond sont écartées : elles exigeraient des polices (glyphes) hébergées en
 * plus ; les engins sont étiquetés par des marqueurs HTML.
 */
export function mapStyle(withBasemap: boolean): StyleSpecification {
  if (!withBasemap) {
    return {
      version: 8,
      sources: {},
      layers: [{ id: "fond-neutre", type: "background", paint: { "background-color": "#eef1f4" } }],
    };
  }
  return {
    version: 8,
    sources: {
      protomaps: { type: "vector", url: `pmtiles://${BASEMAP_PATH}`, attribution: OSM_ATTRIBUTION },
    },
    layers: layers("protomaps", namedFlavor("light"), { lang: "fr" }).filter((layer) => layer.type !== "symbol"),
  };
}
