import { afterEach, describe, expect, it } from "vitest";

import { clearInspectionKit, INSPECTION_KIT_MAX_AGE_MS, loadInspectionKit, saveInspectionKit, type InspectionKit } from "./offlineInspectionKit";

const KEY = "minefleet-field-inspection-kit-v1";
const NOW = Date.parse("2026-11-16T12:00:00Z");
const account = { workspace_code: "espace-fictif", user_account_id: "user-1" };

function kit(extra: Partial<InspectionKit> = {}): InspectionKit {
  return {
    workspace_code: "espace-fictif",
    user_account_id: "user-1",
    saved_at: new Date(NOW - 3600 * 1000).toISOString(),
    sites: [{ site_id: "site-1", code: "MINE", name: "Mine fictive", timezone: "Africa/Conakry" }],
    templates: [
      {
        hse_checklist_template_id: "tpl-1",
        code: "PRE",
        name: "Prise de poste",
        version: 2,
        target_type: "PRE_SHIFT",
        items: [{ key: "epi", label: "EPI portés", critical: true }],
      },
    ],
    vehicles: [{ vehicle_id: "veh-1", site_id: "site-1", fleet_number: "CAM-01" }],
    ...extra,
  };
}

afterEach(() => localStorage.clear());

describe("kit d'inspection hors ligne", () => {
  it("se relit pour le même compte", () => {
    saveInspectionKit(kit());
    expect(loadInspectionKit(account, NOW)).toEqual(kit());
  });

  it("n'est jamais servi à un autre compte ni à un autre espace", () => {
    saveInspectionKit(kit());
    expect(loadInspectionKit({ ...account, user_account_id: "user-2" }, NOW)).toBeNull();
    expect(loadInspectionKit({ ...account, workspace_code: "autre-espace" }, NOW)).toBeNull();
  });

  it("est ignoré au-delà de 7 jours ou s'il est daté dans le futur", () => {
    saveInspectionKit(kit({ saved_at: new Date(NOW - INSPECTION_KIT_MAX_AGE_MS - 1000).toISOString() }));
    expect(loadInspectionKit(account, NOW)).toBeNull();
    saveInspectionKit(kit({ saved_at: new Date(NOW + 3600 * 1000).toISOString() }));
    expect(loadInspectionKit(account, NOW)).toBeNull();
  });

  it("ne conserve que les champs attendus (rien d'inattendu ne transite vers le stockage)", () => {
    const polluted = kit();
    (polluted.templates[0] as unknown as Record<string, unknown>).created_by = "user-9";
    (polluted.vehicles[0] as unknown as Record<string, unknown>).driver_name = "Personne fictive";
    saveInspectionKit(polluted);
    const stored = localStorage.getItem(KEY) ?? "";
    expect(stored).not.toContain("created_by");
    expect(stored).not.toContain("driver_name");
    expect(loadInspectionKit(account, NOW)).toEqual(kit());
  });

  it("refuse un contenu altéré ou incomplet", () => {
    localStorage.setItem(KEY, JSON.stringify({ ...kit(), templates: [{ ...kit().templates[0], target_type: "INCONNU" }] }));
    expect(loadInspectionKit(account, NOW)).toBeNull();
    localStorage.setItem(KEY, "{pas du json");
    expect(loadInspectionKit(account, NOW)).toBeNull();
  });

  it("un kit sans checklist ni site efface le précédent", () => {
    saveInspectionKit(kit());
    saveInspectionKit(kit({ templates: [] }));
    expect(localStorage.getItem(KEY)).toBeNull();
    saveInspectionKit(kit());
    saveInspectionKit(kit({ sites: [] }));
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("s'efface explicitement", () => {
    saveInspectionKit(kit());
    clearInspectionKit();
    expect(loadInspectionKit(account, NOW)).toBeNull();
  });
});
