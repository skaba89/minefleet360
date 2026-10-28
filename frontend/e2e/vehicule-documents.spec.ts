import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Lot 2c : relevé de compteur et document réglementaire depuis la fiche véhicule, liste des échéances.

function isoDay(offsetDays: number): string {
  return new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);
}

test("fiche véhicule : relevé de compteur, document à échéance puis retrait", async ({ page, request }) => {
  test.setTimeout(90_000);
  const ops = account("OPS_MANAGER");
  const opsHeaders = await apiLogin(request, ops);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", ops.workspace)));
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: opsHeaders })).json();
  const truck = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `DOC-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
  const created = await request.post("/api/v1/vehicles", {
    headers: opsHeaders,
    data: { site_id: site, vehicle_category_id: truck.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(created.status(), await created.text()).toBe(201);
  const vehicleId = (await created.json()).vehicle_id;

  await uiLogin(page, ops);
  await page.goto(`/vehicules/${vehicleId}`);

  // 1. Relevé kilométrique.
  await page.getByRole("button", { name: "Nouveau relevé" }).click();
  const reading = page.getByRole("form", { name: "Nouveau relevé de compteur" });
  await reading.getByLabel("Valeur relevée").fill("12345.6");
  await reading.getByRole("button", { name: "Enregistrer le relevé" }).click();
  await expect(page.getByRole("cell", { name: "12 345,6" })).toBeVisible();

  // 2. Assurance qui expire dans cinq jours : bloquante par défaut, signalée « expire bientôt ».
  await page.getByRole("button", { name: "Nouveau document" }).click();
  const doc = page.getByRole("form", { name: "Nouveau document" });
  await doc.getByLabel("Référence (numéro du document)").fill(`POL-${fleetNumber}`);
  await doc.getByLabel("Valable jusqu'au (inclus)").fill(isoDay(5));
  await expect(doc.getByLabel("Bloque l'affectation du véhicule une fois échu")).toBeChecked();
  await doc.getByRole("button", { name: "Enregistrer le document" }).click();
  const row = page.getByRole("row", { name: new RegExp(`POL-${fleetNumber}`) });
  await expect(row).toContainText("Expire bientôt");
  await expect(row).toContainText("Oui");

  // 3. Liste des échéances.
  await page.goto("/vehicules/echeances");
  await expect(page.getByRole("row", { name: new RegExp(fleetNumber) })).toContainText("Assurance");

  // 4. Retrait motivé : le document reste dans l'historique.
  await page.goto(`/vehicules/${vehicleId}`);
  await row.getByRole("button", { name: "Retirer" }).click();
  await page.getByRole("form", { name: `Retirer le document POL-${fleetNumber}` }).getByRole("button", { name: "Retirer le document" }).click();
  await expect(row).toContainText("Retiré");
});
