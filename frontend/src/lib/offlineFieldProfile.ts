/**
 * Profil terrain minimal mémorisé pour ouvrir l'application sans réseau (déclaration HSE uniquement).
 *
 * Contenu volontairement réduit : identifiants du compte et de l'espace, nom affiché, fuseau et sites sur
 * lesquels le compte peut déclarer. Jamais de jeton, d'e-mail ni de donnée métier. Il ne donne aucun accès
 * serveur : toute synchronisation exige une session rétablie pour le même compte.
 */
const KEY = "minefleet-field-profile-v1";

export interface FieldSite {
  site_id: string;
  code: string;
  name: string;
  timezone: string | null;
}

export interface FieldProfile {
  workspace_code: string;
  user_account_id: string;
  display_name: string;
  timezone: string;
  sites: FieldSite[];
}

function storage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

function isText(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 200;
}

function valid(value: unknown): value is FieldProfile {
  if (!value || typeof value !== "object") return false;
  const p = value as Record<string, unknown>;
  return (
    isText(p.workspace_code) &&
    isText(p.user_account_id) &&
    isText(p.display_name) &&
    isText(p.timezone) &&
    Array.isArray(p.sites) &&
    p.sites.length <= 200 &&
    p.sites.every((s) => {
      const site = s as Record<string, unknown>;
      return isText(site.site_id) && isText(site.code) && isText(site.name) && (site.timezone === null || isText(site.timezone));
    })
  );
}

export function saveFieldProfile(profile: FieldProfile): void {
  try {
    const store = storage();
    if (!store) return;
    if (profile.sites.length === 0) store.removeItem(KEY);
    else store.setItem(KEY, JSON.stringify(profile));
  } catch {
    // Stockage plein ou interdit : le mode hors ligne ne sera simplement pas proposé.
  }
}

export function loadFieldProfile(): FieldProfile | null {
  try {
    const raw = storage()?.getItem(KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return valid(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function clearFieldProfile(): void {
  try {
    storage()?.removeItem(KEY);
  } catch {
    // Rien à faire : l'absence de stockage vaut absence de profil.
  }
}
