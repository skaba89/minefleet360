import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Lot 2a : lieux et matières déclarés par l'administration, puis mission conduite par le dispatcher.

test("mission de transport : création, une rotation complète puis clôture", async ({ page, request, browser }) => {
  test.setTimeout(90_000);
  const dispatcher = account("DISPATCHER");
  const dispatcherHeaders = await apiLogin(request, dispatcher);
  const site = await dispatcherSite(request, dispatcherHeaders);
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();

  // 1. Lieux et matière, par l'interface d'administration.
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await uiLogin(admin, account("TENANT_ADMIN", dispatcher.workspace));
  await admin.goto("/administration/lieux-matieres");
  for (const [code, kind] of [
    [`FOS${suffix}`, "Point de chargement"],
    [`VER${suffix}`, "Point de déchargement"],
  ] as const) {
    await admin.getByRole("button", { name: "Nouveau lieu" }).click();
    const form = admin.getByRole("form", { name: "Nouveau lieu" });
    await form.getByRole("combobox", { name: /^Site/ }).selectOption(site);
    await form.getByLabel("Code (unique sur le site)").fill(code);
    await form.getByLabel("Nom", { exact: true }).fill(`Lieu ${code}`);
    await form.getByLabel("Type").selectOption({ label: kind });
    await form.getByRole("button", { name: "Créer le lieu" }).click();
    await expect(admin.getByRole("row", { name: new RegExp(code) })).toBeVisible();
  }
  await admin.getByRole("button", { name: "Nouvelle matière" }).click();
  const materialForm = admin.getByRole("form", { name: "Nouvelle matière" });
  await materialForm.getByLabel("Code (unique)").fill(`BX${suffix}`);
  await materialForm.getByLabel("Nom", { exact: true }).fill(`Bauxite ${suffix}`);
  await materialForm.getByRole("button", { name: "Créer la matière" }).click();
  await expect(admin.getByRole("row", { name: new RegExp(`BX${suffix}`) })).toBeVisible();
  await adminContext.close();

  // 2. Affectation active préparée par l'API (couple éligible).
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });
  const ops = await apiLogin(request, account("OPS_MANAGER", dispatcher.workspace));
  const vehicle = (
    await (await request.get("/api/v1/vehicles", { headers: ops, params: { fleet_number: pair.fleetNumber } })).json()
  ).items[0];
  const driver = (
    await (await request.get("/api/v1/drivers", { headers: ops, params: { q: pair.driverOption.split(" — ")[1]! } })).json()
  ).items[0];
  const assignment = await request.post("/api/v1/vehicle-assignments", {
    headers: ops,
    data: { vehicle_id: vehicle.vehicle_id, driver_id: driver.driver_id, valid_from: new Date().toISOString() },
  });
  expect(assignment.status()).toBe(201);

  // 3. Le dispatcher crée et conduit la mission.
  await uiLogin(page, dispatcher);
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Missions" }).click();
  await page.getByRole("button", { name: "Nouvelle mission" }).click();
  const form = page.getByRole("form", { name: "Nouvelle mission" });
  await form.getByLabel("Véhicule et conducteur (affectation)").selectOption({ label: `${pair.fleetNumber} — ${pair.driverLabel}` });
  await form.getByLabel("Origine").selectOption({ label: `Lieu FOS${suffix} (Point de chargement)` });
  await form.getByLabel("Destination").selectOption({ label: `Lieu VER${suffix} (Point de déchargement)` });
  await form.getByLabel("Matière").selectOption({ label: `Bauxite ${suffix}` });
  await form.getByLabel("Rotations prévues (facultatif)").fill("1");
  await form.getByRole("button", { name: "Créer la mission" }).click();

  const heading = page.getByRole("heading", { name: new RegExp(`Lieu FOS${suffix} → Lieu VER${suffix}`) });
  await expect(heading).toContainText("Affectée");
  for (const [step, state] of [
    ["Départ", "En route à vide"],
    ["Arrivée au chargement", "En chargement"],
    ["Chargement terminé", "En route chargé"],
    ["Arrivée au déchargement", "En déchargement"],
    ["Mission terminée", "Terminée"],
  ] as const) {
    await page.getByRole("button", { name: step, exact: true }).click();
    await expect(heading).toContainText(state);
  }
  await expect(page.getByRole("row", { name: /^1 / })).toContainText("Terminée");
  await expect(page.locator(".timeline li")).toHaveCount(6);
  await expect(page.getByRole("button", { name: "Départ", exact: true })).toHaveCount(0);
});

test("un rôle en lecture seule voit les missions sans bouton d'action", async ({ page }) => {
  await uiLogin(page, account("AUDITOR"));
  await page.goto("/missions");
  await expect(page.getByRole("heading", { name: "Missions de transport" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouvelle mission" })).toHaveCount(0);
});
