/**
 * Kit d'inspection hors ligne (phase 3, tranche 3) : ce qu'il faut pour réaliser une inspection HSE quand
 * l'application s'ouvre sans réseau.
 *
 * Contenu volontairement borné, sans donnée personnelle ni jeton : sites où le compte peut inspecter,
 * définitions des checklists actives, engins de ces sites (identifiant + numéro de parc). Lié au compte qui l'a
 * préparé, relu avec validation stricte, ignoré au-delà de 7 jours, supprimé à la déconnexion volontaire.
 * Il ne donne aucun accès serveur : chaque inspection reste revérifiée à la synchronisation (permission, site,
 * modèle toujours actif, engin du site).
 */
const KEY = "minefleet-field-inspection-kit-v1";
export const INSPECTION_KIT_MAX_AGE_MS = 7 * 24 * 3600 * 1000;
const MAX_SITES = 50;
const MAX_TEMPLATES = 50;
const MAX_ITEMS = 100;
const MAX_VEHICLES = 1000;

export type KitTargetType = "PRE_SHIFT" | "VEHICLE" | "WORK_AREA";

export interface KitSite {
  site_id: string;
  code: string;
  name: string;
  timezone: string | null;
}

export interface KitTemplate {
  hse_checklist_template_id: string;
  code: string;
  name: string;
  version: number;
  target_type: KitTargetType;
  items: { key: string; label: string; critical: boolean }[];
}

export interface KitVehicle {
  vehicle_id: string;
  site_id: string;
  fleet_number: string;
}

export interface InspectionKit {
  workspace_code: string;
  user_account_id: string;
  saved_at: string;
  sites: KitSite[];
  templates: KitTemplate[];
  vehicles: KitVehicle[];
}

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function isText(value: unknown, max = 200): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function validSite(value: unknown): value is KitSite {
  const s = value as Record<string, unknown> | null;
  return !!s && isText(s.site_id) && isText(s.code) && isText(s.name) && (s.timezone === null || isText(s.timezone));
}

function validTemplate(value: unknown): value is KitTemplate {
  const t = value as Record<string, unknown> | null;
  return (
    !!t &&
    isText(t.hse_checklist_template_id) &&
    isText(t.code) &&
    isText(t.name) &&
    Number.isInteger(t.version) &&
    (t.version as number) > 0 &&
    (t.target_type === "PRE_SHIFT" || t.target_type === "VEHICLE" || t.target_type === "WORK_AREA") &&
    Array.isArray(t.items) &&
    t.items.length > 0 &&
    t.items.length <= MAX_ITEMS &&
    t.items.every((raw) => {
      const i = raw as Record<string, unknown> | null;
      return !!i && isText(i.key, 100) && isText(i.label, 500) && typeof i.critical === "boolean";
    })
  );
}

function validVehicle(value: unknown): value is KitVehicle {
  const v = value as Record<string, unknown> | null;
  return !!v && isText(v.vehicle_id) && isText(v.site_id) && isText(v.fleet_number);
}

function valid(value: unknown): value is InspectionKit {
  if (!value || typeof value !== "object") return false;
  const k = value as Record<string, unknown>;
  return (
    isText(k.workspace_code) &&
    isText(k.user_account_id) &&
    isText(k.saved_at) &&
    Number.isFinite(Date.parse(k.saved_at as string)) &&
    Array.isArray(k.sites) &&
    k.sites.length > 0 &&
    k.sites.length <= MAX_SITES &&
    k.sites.every(validSite) &&
    Array.isArray(k.templates) &&
    k.templates.length > 0 &&
    k.templates.length <= MAX_TEMPLATES &&
    k.templates.every(validTemplate) &&
    Array.isArray(k.vehicles) &&
    k.vehicles.length <= MAX_VEHICLES &&
    k.vehicles.every(validVehicle)
  );
}

/** Ne garde que les champs attendus (aucun champ inattendu ne transite vers le stockage local). */
function minimal(kit: InspectionKit): InspectionKit {
  return {
    workspace_code: kit.workspace_code,
    user_account_id: kit.user_account_id,
    saved_at: kit.saved_at,
    sites: kit.sites.map(({ site_id, code, name, timezone }) => ({ site_id, code, name, timezone })),
    templates: kit.templates.map(({ hse_checklist_template_id, code, name, version, target_type, items }) => ({
      hse_checklist_template_id,
      code,
      name,
      version,
      target_type,
      items: items.map(({ key, label, critical }) => ({ key, label, critical })),
    })),
    vehicles: kit.vehicles.map(({ vehicle_id, site_id, fleet_number }) => ({ vehicle_id, site_id, fleet_number })),
  };
}

/** Enregistre le kit ; un kit vide (aucun site ou aucune checklist) efface le précédent. */
export function saveInspectionKit(kit: InspectionKit): void {
  try {
    const store = storage();
    if (!store) return;
    const clean = minimal(kit);
    if (!valid(clean)) {
      store.removeItem(KEY);
      return;
    }
    store.setItem(KEY, JSON.stringify(clean));
  } catch {
    // Stockage plein ou interdit : l'inspection hors ligne ne sera simplement pas proposée.
  }
}

/** Kit utilisable pour CE compte, préparé il y a moins de 7 jours ; sinon null. */
export function loadInspectionKit(account: { workspace_code: string; user_account_id: string }, now = Date.now()): InspectionKit | null {
  try {
    const raw = storage()?.getItem(KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!valid(parsed)) return null;
    if (parsed.workspace_code !== account.workspace_code || parsed.user_account_id !== account.user_account_id) return null;
    const age = now - Date.parse(parsed.saved_at);
    if (age < 0 || age > INSPECTION_KIT_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearInspectionKit(): void {
  try {
    storage()?.removeItem(KEY);
  } catch {
    // Rien à faire : l'absence de stockage vaut absence de kit.
  }
}
