import { expect, it, vi } from "vitest";

import { availableBasemaps, basemapAvailable, mapStyle } from "./basemap";

it("considère le fond absent si le serveur renvoie la page de l'application ou une erreur", async () => {
  expect(await basemapAvailable(vi.fn(async () => new Response("<html>", { status: 200, headers: { "content-type": "text/html" } })))).toBe(false);
  expect(await basemapAvailable(vi.fn(async () => new Response("", { status: 404 })))).toBe(false);
  expect(await basemapAvailable(vi.fn(async () => { throw new Error("réseau"); }))).toBe(false);
  expect(await basemapAvailable(vi.fn(async () => new Response("", { status: 200, headers: { "content-type": "application/octet-stream" } })))).toBe(true);
});

it("style : fond neutre sans fichier ; tuiles locales sans couche de texte avec le fichier", () => {
  expect(mapStyle(false).sources).toEqual({});
  const style = mapStyle(true);
  expect(JSON.stringify(style.sources)).toContain("pmtiles:///basemap/guinee.pmtiles");
  expect(JSON.stringify(style.sources)).toContain("OpenStreetMap");
  expect(style.layers.length).toBeGreaterThan(5);
  expect(style.layers.some((layer) => layer.type === "symbol")).toBe(false);
});

it("détecte séparément les fonds Guinée et France", async () => {
  const fetcher = vi.fn(async (url: RequestInfo | URL) =>
    new Response("", { status: String(url).includes("france") ? 200 : 404 }),
  ) as typeof fetch;
  expect(await availableBasemaps(fetcher)).toEqual(["france"]);
});

it("compose deux sources PMTiles locales avec des identifiants de couches uniques", () => {
  const style = mapStyle(["guinee", "france"]);
  expect(Object.keys(style.sources ?? {})).toEqual(["protomaps-guinee", "protomaps-france"]);
  expect(JSON.stringify(style.sources)).toContain("pmtiles:///basemap/france.pmtiles");
  expect(JSON.stringify(style.sources)).toContain("pmtiles:///basemap/guinee.pmtiles");
  const ids = style.layers.map((layer) => layer.id);
  expect(ids.length).toBe(new Set(ids).size);
  expect(style.layers.filter((layer) => layer.type === "background")).toHaveLength(1);
  expect(style.layers.some((layer) => layer.type === "symbol")).toBe(false);
  expect(style.layers.some((layer) => layer.id.startsWith("france-"))).toBe(true);
  expect(style.layers.some((layer) => layer.id.startsWith("guinee-"))).toBe(true);
});
