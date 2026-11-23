import { describe, expect, it } from "vitest";

import { readPolygonDraft } from "./GeofenceDrawMap";

describe("readPolygonDraft", () => {
  it("supports the same latitude, longitude order as the existing form", () => {
    expect(readPolygonDraft("9.641200, -13.578400\n9.642100, -13.577300")).toEqual([
      [-13.5784, 9.6412],
      [-13.5773, 9.6421],
    ]);
  });

  it("returns an empty draft on malformed or out-of-range coordinates", () => {
    expect(readPolygonDraft("9.6, -13.5\nnot a coordinate")).toEqual([]);
    expect(readPolygonDraft("91, -13")).toEqual([]);
    expect(readPolygonDraft("9.6, -181")).toEqual([]);
    expect(readPolygonDraft("9.6, -13, 0")).toEqual([]);
  });

  it("does not convert an empty draft into a polygon", () => {
    expect(readPolygonDraft(" \n ")).toEqual([]);
  });
});
