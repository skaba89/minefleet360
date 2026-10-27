import { describe, expect, it } from "vitest";

import { can } from "./permissions";

const S1 = "11111111-1111-4111-8111-111111111111";
const S2 = "22222222-2222-4222-8222-222222222222";

describe("affichage conditionnel des actions", () => {
  it("dispatcher : écriture sur son site seulement", () => {
    const grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: S1 }];
    expect(can(grants, "assignment.vehicle_assignment.create", S1)).toBe(true);
    expect(can(grants, "assignment.vehicle_assignment.create", S2)).toBe(false);
  });

  it("administrateur du tenant : pas d'accès aux affectations ni aux conducteurs (D-10)", () => {
    const grants = [{ role_code: "TENANT_ADMIN", scope_type: "TENANT", site_id: null }];
    expect(can(grants, "assignment.vehicle_assignment.read")).toBe(false);
    expect(can(grants, "workforce.driver.read")).toBe(false);
    expect(can(grants, "fleet.vehicle.read")).toBe(true);
  });

  it("RH lit les affectations sans pouvoir en créer", () => {
    const grants = [{ role_code: "HR", scope_type: "TENANT", site_id: null }];
    expect(can(grants, "assignment.vehicle_assignment.read")).toBe(true);
    expect(can(grants, "assignment.vehicle_assignment.create")).toBe(false);
  });
});
