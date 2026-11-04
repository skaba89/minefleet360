import "maplibre-gl/dist/maplibre-gl.css";

import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Protocol } from "pmtiles";

import { basemapAvailable, mapStyle } from "./basemap";

export const GUINEA_CENTER: [number, number] = [-11.3, 10.4];

let protocolRegistered = false;
maplibregl.setWorkerUrl(workerUrl);

export function reducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Carte MapLibre sur le fond auto-hébergé s'il est servi (sinon fond neutre). Lève une erreur si WebGL est
 * indisponible : l'appelant affiche alors une alternative textuelle.
 */
export async function createMap(container: HTMLElement): Promise<{ map: maplibregl.Map; withBasemap: boolean }> {
  const withBasemap = await basemapAvailable();
  if (withBasemap && !protocolRegistered) {
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolRegistered = true;
  }
  const map = new maplibregl.Map({
    container,
    style: mapStyle(withBasemap),
    center: GUINEA_CENTER,
    zoom: 6,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  return { map, withBasemap };
}
