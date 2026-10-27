import { expect, test, type APIRequestContext } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Lot 2b : saisie manuelle d'une pesée par le dispatcher, approbation par une autre personne, indicateurs.

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

test("pesée manuelle : saisie, approbation par un autre utilisateur, puis indicateurs", async ({ page, request, browser }) => {
  test.setTimeout(90_000);
  const dispatcher = account("DISPATCHER");
  const dispatcherHeaders = await apiLogin(request, dispatcher);
  const site = await dispatcherSite(request, dispatcherHeaders);
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const admin = await apiLogin(request, account("TENANT_ADMIN", dispatcher.workspace));
  const place = (code: string, kind: string) =>
    post(request, "/api/v1/site-locations", admin, { site_id: site, code, name: `Lieu ${code}`, kind });
  const origin = await place(`FOS${suffix}`, "LOADING_POINT");
  const destination = await place(`VER${suffix}`, "DUMP_POINT");
  await place(`PONT${suffix}`, "WEIGHBRIDGE");
  const material = await post(request, "/api/v1/materials", admin, { code: `BX${suffix}`, name: `Bauxite ${suffix}` });

  // Mission préparée par l'API jusqu'au déchargement de la première rotation.
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });
  const ops = await apiLogin(request, account("OPS_MANAGER", dispatcher.workspace));
  const vehicle = (
    await (await request.get("/api/v1/vehicles", { headers: ops, params: { fleet_number: pair.fleetNumber } })).json()
  ).items[0];
  const driver = (
    await (await request.get("/api/v1/drivers", { headers: ops, params: { q: pair.driverOption.split(" — ")[1]! } })).json()
  ).items[0];
  const assignment = await post(request, "/api/v1/vehicle-assignments", ops, {
    vehicle_id: vehicle.vehicle_id,
    driver_id: driver.driver_id,
    valid_from: new Date().toISOString(),
  });
  const mission = await post(request, "/api/v1/missions", ops, {
    vehicle_assignment_id: assignment.vehicle_assignment_id,
    origin_location_id: origin.site_location_id,
    destination_location_id: destination.site_location_id,
    material_id: material.material_id,
    planned_start: new Date().toISOString(),
  });
  const url = `/api/v1/missions/${mission.mission_id}`;
  for (const event_type of ["DEPARTED", "ARRIVED_LOADING", "LOADED", "ARRIVED_UNLOADING", "COMPLETED"]) {
    const etag = (await request.get(url, { headers: ops })).headers()["etag"]!;
    await post(request, `${url}/events`, { ...ops, "If-Match": etag }, { event_type });
  }

  // 1. Le dispatcher saisit la pesée depuis la fiche mission (pont en panne).
  await uiLogin(page, dispatcher);
  await page.goto(`/missions/${mission.mission_id}`);
  await page.getByRole("button", { name: "Saisir la pesée" }).click();
  const form = page.getByRole("form", { name: "Nouvelle pesée" });
  await form.getByRole("combobox", { name: "Pont-bascule", exact: true }).selectOption({ label: `Lieu PONT${suffix}` });
  await form.getByLabel("Numéro du ticket").fill(`M-${suffix}`);
  await form.getByRole("combobox", { name: "Source", exact: true }).selectOption("MANUAL_DEGRADED");
  await form.getByLabel("Motif de la saisie manuelle").selectOption("POWER_OUTAGE");
  await form.getByLabel("Poids brut (kg)").fill("52000");
  await form.getByLabel("Tare (kg)").fill("18000");
  await expect(form).toContainText("34,00");
  await form.getByRole("button", { name: "Enregistrer la pesée" }).click();
  const rotationRow = page.getByRole("row", { name: /^1 / });
  await expect(rotationRow).toContainText("À approuver");
  await expect(page.getByRole("button", { name: "Saisir la pesée" })).toHaveCount(0);

  // 2. Le responsable des opérations (autre personne) l'approuve.
  const opsContext = await browser.newContext();
  const opsPage = await opsContext.newPage();
  await uiLogin(opsPage, account("OPS_MANAGER", dispatcher.workspace));
  await opsPage.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Pesées" }).click();
  const ticketRow = opsPage.getByRole("row", { name: new RegExp(`M-${suffix}`) });
  await expect(ticketRow).toContainText("À approuver");
  await ticketRow.getByRole("button", { name: "Approuver" }).click();
  await expect(ticketRow).toContainText("Valide");

  // 3. Indicateurs : la rotation compte désormais comme mesurée.
  await opsPage.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Indicateurs" }).click();
  const indicatorRow = opsPage.getByRole("row", { name: new RegExp(`Bauxite ${suffix}`) });
  await expect(indicatorRow).toContainText("34,00");
  await expect(indicatorRow).toContainText("1 rotation(s) pesée(s)");
  await opsContext.close();
});

test("un rôle sans droit sur les pesées ne voit pas le menu", async ({ page }) => {
  await uiLogin(page, account("HR"));
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Conducteurs" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Pesées" })).toHaveCount(0);
});
