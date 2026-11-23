import { layers, namedFlavor } from "@protomaps/basemaps";
import type { StyleSpecification } from "maplibre-gl";

/** Regional PMTiles are self-hosted: GPS coordinates are never sent to external tile providers. */
export const BASEMAP_PATH = "/basemap/guinee.pmtiles";
export const FRANCE_BASEMAP_PATH = "/basemap/france.pmtiles";
export const OSM_ATTRIBUTION = "© contributeurs OpenStreetMap (ODbL)";
export type BasemapRegion = "guinee" | "france";
export const BASEMAPS: Record<BasemapRegion, string> = {
  guinee: BASEMAP_PATH,
  france: FRANCE_BASEMAP_PATH,
};

async function archiveAvailable(path: string, fetcher: typeof fetch): Promise<boolean> {
  try {
    const response = await fetcher(path, { method: "HEAD" });
    const type = response.headers.get("content-type") ?? "";
    return response.ok && !type.includes("text/html");
  } catch {
    return false;
  }
}

/** Backwards-compatible single-region check used in existing tests. */
export async function basemapAvailable(fetcher: typeof fetch = fetch): Promise<boolean> {
  return archiveAvailable(BASEMAP_PATH, fetcher);
}

/** Check each optional regional file independently; one missing archive must not hide another. */
export async function availableBasemaps(fetcher: typeof fetch = fetch): Promise<BasemapRegion[]> {
  const [guinee, france] = await Promise.all([
    archiveAvailable(BASEMAP_PATH, fetcher),
    archiveAvailable(FRANCE_BASEMAP_PATH, fetcher),
  ]);
  return [ ...(guinee ? (["guinee"] as const) : []), ...(france ? (["france"] as const) : []) ];
}

/**
 * Combine disjoint regional tiles into one MapLibre style with unique sources and layer IDs.
 * Keep a single neutral background. Exclude symbol layers (no local glyphs yet).
 */
export function mapStyle(regions: boolean | readonly BasemapRegion[]): StyleSpecification {
  const available: readonly BasemapRegion[] = typeof regions === "boolean" ? (regions ? ["guinee"] : []) : regions;
  if (available.length === 0) {
    return {
      version: 8,
      sources: {},
      layers: [{ id: "fond-neutre", type: "background", paint: { "background-color": "#eef1f4" } }],
    };
  }

  const sources: StyleSpecification["sources"] = {};
  const baseLayers: StyleSpecification["layers"] = [
    { id: "fond-neutre", type: "background", paint: { "background-color": "#eef1f4" } },
  ];
  for (const region of available) {
    const sourceId = `protomaps-${region}`;
    sources[sourceId] = {
      type: "vector",
      url: `pmtiles://${BASEMAPS[region]}`,
      attribution: OSM_ATTRIBUTION,
    };
    for (const layer of layers(sourceId, namedFlavor("light"), { lang: "fr" })) {
      if (layer.type === "symbol" || layer.type === "background") continue;
      baseLayers.push({ ...layer, id: `${region}-${layer.id}` });
    }
  }
  return { version: 8, sources, layers: baseLayers };
}
