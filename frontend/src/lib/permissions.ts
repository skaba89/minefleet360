// Affichage conditionnel des actions. Le serveur reste seul juge (403) : ceci évite seulement de
// proposer un bouton voué à l'échec. Règles générées depuis authz_matrix.yaml (permissions.generated.ts).
import type { Schemas } from "../api/client";
import { GRANTS, type Permission } from "./permissions.generated";

export type { Permission };

type Grant = Schemas["GrantOut"];

/**
 * Vrai si une attribution porte la permission. Avec `siteId`, la portée SITE doit viser ce site ;
 * sans `siteId`, une attribution de portée SITE suffit (au moins un site).
 */
export function can(grants: readonly Grant[], permission: Permission, siteId?: string | null): boolean {
  const rule: Partial<Record<string, readonly string[]>> = GRANTS[permission];
  return grants.some((g) => {
    if (!(rule[g.role_code] ?? []).includes(g.scope_type)) return false;
    return g.scope_type !== "SITE" || !siteId || g.site_id === siteId;
  });
}
