import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : maintenance préventive — création de plan, révision (nouvelle version),
// évaluation réelle des échéances puis suspension motivée. Le cycle DUE → planifier → OT
// (compteurs, insuffisance de données, courses d'évaluation) reste couvert par la suite pytest
// dédiée (test_preventive_*.py) ; cette spec prouve le parcours responsable d'atelier depuis l'UI.
const WORKSPACE = "fictif-transport";

test("préventif : plan créé, échéances évaluées, révision v2 puis suspension motivée", async ({ page, request }) => {
  test.setTimeout(120_000);
  const ops = await apiLogin(request, account("OPS_MANAGER", WORKSPACE));
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", WORKSPACE)));
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: ops })).json();
  const truck = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const fleetNumber = `PVT-${suffix}`;
  const planCode = `P-E2E-${suffix}`;
  const vehicle = await request.post("/api/v1/vehicles", {
    headers: ops,
    data: { site_id: site, vehicle_category_id: truck.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(vehicle.status(), await vehicle.text()).toBe(201);

  await uiLogin(page, account("WORKSHOP_CHIEF", WORKSPACE));
  await page.goto("/maintenance");
  await page.getByRole("combobox", { name: "Véhicule", exact: true }).selectOption({ label: fleetNumber });

  const plans = page.getByRole("region", { name: "Plans de maintenance préventive" });

  // 1. Création d'un plan à 30 jours depuis l'UI.
  const createForm = plans.locator("form").filter({ hasText: "Créer un plan" });
  await createForm.getByLabel("Code du plan").fill(planCode);
  await createForm.getByLabel("Jours", { exact: true }).fill("30");
  await createForm.getByRole("button", { name: "Créer le plan" }).click();
  const row = page.getByRole("row", { name: new RegExp(planCode) });
  await expect(row).toContainText("Actif");
  await expect(row).toContainText("30 jours");

  // 2. Évaluation réelle des échéances (tous les sites autorisés) : le plan à 30 jours d'un engin
  //    neuf donne une échéance à venir, comptée et affichée en français.
  await page.getByRole("button", { name: "Évaluer les échéances" }).click();
  const evaluation = page.getByRole("status").filter({ hasText: "plan(s) évalué(s)" });
  await expect(evaluation).toContainText("plan(s) évalué(s)");
  await expect(evaluation).toContainText("à venir");

  // 3. Révision : la périodicité passe à 90 jours, une nouvelle version (v2) devient la ligne active
  //    — l'historique reste visible (la v1 à 30 jours reste dans la table).
  await row.getByRole("button", { name: "Réviser" }).click();
  const reviseForm = row.locator("form");
  await reviseForm.getByLabel("Jours", { exact: true }).fill("90");
  await reviseForm.getByRole("button", { name: "Confirmer la révision" }).click();
  const revisedRow = page.getByRole("row", { name: new RegExp(`${planCode} 2 90 jours`) });
  await expect(revisedRow).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(`${planCode} 1 30 jours`) })).toBeVisible();

  // 4. Suspension motivée : le motif s'affiche dans l'état de la version active.
  await revisedRow.getByRole("button", { name: "Suspendre" }).click();
  await revisedRow.getByLabel("Motif de suspension").fill("Attente de pièces constructeur (motif E2E)");
  await revisedRow.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect(revisedRow).toContainText("Suspendu —");
  await expect(revisedRow).toContainText("Attente de pièces constructeur");
});
