import { describe, expect, it } from "vitest";

import { vehicleTypeIcon } from "./vehicleTypeIcon";

describe("vehicleTypeIcon", () => {
  it.each([
    ["RIGID_DUMP_TRUCK", "🚚"],
    ["ARTICULATED_DUMP_TRUCK", "🚚"],
    ["ROAD_DUMP_TRUCK", "🚚"],
    ["FUEL_TANKER", "🚚"],
    ["WHEEL_LOADER", "🚜"],
    ["HYDRAULIC_EXCAVATOR", "🚜"],
    ["BULLDOZER", "🚜"],
    ["MOTOR_GRADER", "🚜"],
    ["PERSONNEL_BUS", "🚌"],
    ["LIGHT_VEHICLE", "🚙"],
  ])("renders %s as %s", (code, expected) => {
    expect(vehicleTypeIcon({ code })).toBe(expected);
  });

  it("provides a generic fallback without an icon saved per vehicle", () => {
    expect(vehicleTypeIcon(undefined)).toBe("🚗");
    expect(vehicleTypeIcon({ code: "UNKNOWN_CATEGORY" })).toBe("🚗");
  });

  it("can use the existing category family as a fallback", () => {
    expect(vehicleTypeIcon({ code: "CUSTOM_MACHINE", family: "MINING" })).toBe("🚜");
  });
});
