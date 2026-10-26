// Affichage conditionnel des actions. Le serveur reste seul juge (403) : ceci évite seulement de
// proposer un bouton voué à l'échec. Source : backend/app/authz/authz_matrix.yaml (à tenir alignée).
import type { Schemas } from "../api/client";

type Grant = Schemas["GrantOut"];

const RULES: Record<string, Partial<Record<string, readonly string[]>>> = {
  "fleet.vehicle.read": {
    TENANT_ADMIN: ["TENANT"], DIRECTION: ["TENANT"], OPS_MANAGER: ["TENANT", "SITE"], DISPATCHER: ["SITE"],
    WORKSHOP_CHIEF: ["SITE"], MECHANIC: ["SITE"], STOREKEEPER: ["SITE"], FUEL_MANAGER: ["SITE"],
    HSE: ["TENANT", "SITE"], FINANCE: ["TENANT", "SITE"], AUDITOR: ["TENANT"],
  },
  "workforce.driver.read": {
    DIRECTION: ["TENANT"], OPS_MANAGER: ["TENANT", "SITE"], DISPATCHER: ["SITE"], HR: ["TENANT", "SITE"],
    WORKSHOP_CHIEF: ["SITE"], FUEL_MANAGER: ["SITE"], HSE: ["TENANT", "SITE"], AUDITOR: ["TENANT"],
  },
  "assignment.vehicle_assignment.read": {
    DIRECTION: ["TENANT"], OPS_MANAGER: ["TENANT", "SITE"], DISPATCHER: ["SITE"], HR: ["TENANT", "SITE"],
    WORKSHOP_CHIEF: ["SITE"], FUEL_MANAGER: ["SITE"], HSE: ["TENANT", "SITE"], AUDITOR: ["TENANT"],
  },
  "assignment.vehicle_assignment.write": { OPS_MANAGER: ["TENANT", "SITE"], DISPATCHER: ["SITE"] },
};

export type UiPermission = keyof typeof RULES;

/** Vrai si une attribution porte la permission (sur `siteId` si fourni). */
export function can(grants: readonly Grant[], permission: UiPermission, siteId?: string | null): boolean {
  const rule = RULES[permission] ?? {};
  return grants.some((g) => {
    if (!(rule[g.role_code] ?? []).includes(g.scope_type)) return false;
    return g.scope_type !== "SITE" || !siteId || g.site_id === siteId;
  });
}
