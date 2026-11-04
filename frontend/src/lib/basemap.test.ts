import { expect, it, vi } from "vitest";

import { basemapAvailable, mapStyle } from "./basemap";

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
