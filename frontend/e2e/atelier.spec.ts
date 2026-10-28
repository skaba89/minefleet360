import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Lot 3a : panne signalée par le dispatcher, intervention par le chef d'atelier, remise en service
// validée par une autre personne (exploitation). Espace « fictif-transport » : le chef d'atelier de
// l'autre espace sert au test de double authentification.
const WORKSPACE = "fictif-transport";

test("panne bloquante : signalement, intervention, remise en service par une autre personne", async ({ page, request, browser }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER", WORKSPACE);
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const ops = await apiLogin(request, account("OPS_MANAGER", WORKSPACE));
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: ops })).json();
  const truck = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `OT-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
  const vehicle = await request.post("/api/v1/vehicles", {
    headers: ops,
    data: { site_id: site, vehicle_category_id: truck.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(vehicle.status(), await vehicle.text()).toBe(201);
  const vehicleId = (await vehicle.json()).vehicle_id;

  // 1. Le dispatcher signale une panne bloquante.
  await uiLogin(page, dispatcher);
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Atelier" }).click();
  await page.getByRole("button", { name: "Signaler une panne" }).click();
  const report = page.getByRole("form", { name: "Signaler une panne" });
  await report.getByRole("combobox", { name: "Véhicule", exact: true }).selectOption({ label: fleetNumber });
  await report.getByRole("combobox", { name: "Type de panne" }).selectOption("BRAKES");
  await report.getByLabel("Panne bloquante : immobiliser le véhicule (sa mission en cours est suspendue)").check();
  await report.getByRole("button", { name: "Enregistrer le signalement" }).click();
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toContainText("Demandé");
  await expect(page.getByRole("button", { name: "Approuver" })).toHaveCount(0); // pas de droit de décision
  const orderUrl = page.url();

  // 2. Le chef d'atelier approuve, s'assigne et réalise l'intervention.
  const chiefContext = await browser.newContext();
  const chief = await chiefContext.newPage();
  await uiLogin(chief, account("WORKSHOP_CHIEF", WORKSPACE));
  await chief.goto(orderUrl);
  const chiefHeading = chief.getByRole("heading", { level: 1 });
  await chief.getByRole("button", { name: "Approuver" }).click();
  await chief.getByRole("form", { name: "Approuver la demande" }).getByRole("button", { name: "Approuver" }).click();
  await expect(chiefHeading).toContainText("Approuvé");
  await chief.getByRole("button", { name: "Assigner un mécanicien" }).click();
  const assign = chief.getByRole("form", { name: "Assigner un mécanicien" });
  await assign.getByRole("combobox", { name: "Mécanicien" }).selectOption({ index: 1 });
  await assign.getByRole("button", { name: "Assigner" }).click();
  await expect(chiefHeading).toContainText("Assigné");
  await chief.getByRole("button", { name: "Démarrer l'intervention" }).click();
  await expect(chiefHeading).toContainText("En cours");
  const reportForm = chief.getByRole("form", { name: "Compte rendu d'intervention" });
  await reportForm.getByLabel("Travaux réalisés").fill("Plaquettes et disques remplacés");
  await reportForm.getByRole("button", { name: "Travaux terminés : passer au contrôle" }).click();
  await expect(chiefHeading).toContainText("Contrôle qualité");
  await chief.getByRole("button", { name: "Contrôle conforme : remettre en service" }).click();
  await expect(chief.getByRole("alert")).toContainText("autre personne"); // pas d'auto-validation
  await chiefContext.close();

  // 3. L'exploitation valide la remise en service : le véhicule redevient disponible.
  const opsContext = await browser.newContext();
  const opsPage = await opsContext.newPage();
  await uiLogin(opsPage, account("OPS_MANAGER", WORKSPACE));
  await opsPage.goto(orderUrl);
  await opsPage.getByRole("button", { name: "Contrôle conforme : remettre en service" }).click();
  await expect(opsPage.getByRole("heading", { level: 1 })).toContainText("Clôturé");
  await expect(opsPage.locator(".timeline")).toContainText("Remise en service");
  await opsPage.goto(`/vehicules/${vehicleId}`);
  await expect(opsPage.getByRole("heading", { level: 1 })).toContainText("Disponible");
  await opsContext.close();
});
