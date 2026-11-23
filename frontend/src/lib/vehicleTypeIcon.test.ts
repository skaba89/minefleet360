import { describe, expect, it } from "vitest";

import { fleetIconHref, vehicleTypeIcon } from "./vehicleTypeIcon";

describe("vehicleTypeIcon", () => {
  it.each([
    ["RIGID_DUMP_TRUCK", "dump-truck"],
    ["ARTICULATED_DUMP_TRUCK", "articulated-truck"],
    ["ROAD_DUMP_TRUCK", "road-truck"],
    ["FUEL_TANKER", "tanker"],
    ["WATER_TANKER", "tanker"],
    ["WHEEL_LOADER", "loader"],
    ["HYDRAULIC_EXCAVATOR", "excavator"],
    ["BULLDOZER", "bulldozer"],
    ["MOTOR_GRADER", "grader"],
    ["PERSONNEL_BUS", "bus"],
    ["LIGHT_VEHICLE", "pickup"],
    ["MOTORCYCLE", "motorcycle"],
    ["MOBILE_CRANE", "crane"],
  ])("uses the SVG icon %s → %s", (code, expected) => {
    expect(vehicleTypeIcon({ code })).toBe(expected);
  });

  it("falls back safely when the category is missing or unknown", () => {
    expect(vehicleTypeIcon(undefined)).toBe("fleet");
    expect(vehicleTypeIcon({ code: "UNKNOWN_CATEGORY" })).toBe("fleet");
  });

  it("uses the family only if the code is not recognised", () => {
    expect(vehicleTypeIcon({ code: "CUSTOM_MACHINE", family: "MINING" })).toBe("loader");
  });

  it("references same-origin self-hosted SVG symbols", () => {
    expect(fleetIconHref("excavator")).toBe("/fleet-icons.svg#excavator");
  });
});
