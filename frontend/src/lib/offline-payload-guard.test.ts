import { describe, expect, it } from "vitest";

import { assertOfflinePayloadSafe } from "./offline-payload-guard";

describe("garde-fous des données terrain", () => {
  it("accepte des données métier JSON non sensibles", () => {
    expect(() => assertOfflinePayloadSafe({ event: "NOTE", details: ["panne", 2] })).not.toThrow();
  });

  it("refuse des secrets même imbriqués", () => {
    expect(() => assertOfflinePayloadSafe({ nested: [{ refreshToken: "test" }] })).toThrow("sensible");
    expect(() => assertOfflinePayloadSafe({ authorization: "Bearer example" })).toThrow("sensible");
    expect(() => assertOfflinePayloadSafe({ api_key: "x" })).toThrow("sensible");
  });

  it("refuse les références circulaires", () => {
    const cycle: Record<string, unknown> = {};
    cycle.self = cycle;
    expect(() => assertOfflinePayloadSafe(cycle)).toThrow("circulaire");
  });

  it("refuse les objets non JSON", () => {
    expect(() => assertOfflinePayloadSafe({ timestamp: new Date() })).toThrow("JSON");
  });
});
