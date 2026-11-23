import { describe, expect, it } from "vitest";

import { zonesGeoJSON } from "./GeofenceOverviewMap";

describe("zonesGeoJSON", () => {
  it("preserves closed GeoJSON rings and zone metadata", () => {
    const zones = [{
      site_geofence_id: "zone-1",
      name: "Accès interdit",
      kind: "RESTRICTED",
      coordinates: [[-13.5, 9.6], [-13.4, 9.6], [-13.4, 9.7], [-13.5, 9.6]] as [number, number][],
    }];
    expect(zonesGeoJSON(zones).features).toEqual([{
      type: "Feature",
      properties: { id: "zone-1", name: "Accès interdit", kind: "RESTRICTED" },
      geometry: { type: "Polygon", coordinates: [zones[0]!.coordinates] },
    }]);
  });

  it("excludes incomplete rings instead of rendering invalid polygons", () => {
    expect(zonesGeoJSON([{ site_geofence_id: "incomplete", name: "Test", kind: "OTHER",
      coordinates: [[-13, 9], [-12, 9], [-12, 10]] }]).features).toEqual([]);
    expect(zonesGeoJSON([]).features).toEqual([]);
  });
});
