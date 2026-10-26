import { expect, test } from "@playwright/test";

import { account, accounts, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Parcours du plan du lot 1 (PLAN_LOT1 §1, tranche 1c) : affecter puis clôturer, refus d'inéligibilité,
// cloisonnement entre sociétés. Données fictives uniquement.

test("le dispatcher affecte un conducteur puis clôture l'affectation", async ({ page, request }) => {
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });

  await uiLogin(page, dispatcher);
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Affectations" }).click();
  await page.getByRole("button", { name: "Nouvelle affectation" }).click();
  const form = page.getByRole("form", { name: "Nouvelle affectation" });
  await form.getByLabel("Véhicule disponible").selectOption({ label: pair.fleetNumber });
  await form.getByLabel("Conducteur actif du même site").selectOption({ label: pair.driverOption });
  await form.getByRole("button", { name: "Affecter" }).click();
  await expect(form.getByRole("status")).toContainText("Affectation enregistrée (Active)");

  const row = page.getByRole("row", { name: new RegExp(pair.fleetNumber) });
  await expect(row).toContainText("Conforme");
  await row.getByRole("button", { name: "Clôturer" }).click();
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(row).toContainText("Terminée");
});

test("une affectation inéligible est refusée avec ses motifs en français", async ({ page, request }) => {
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: false });

  await uiLogin(page, dispatcher);
  await page.goto("/affectations");
  await page.getByRole("button", { name: "Nouvelle affectation" }).click();
  const form = page.getByRole("form", { name: "Nouvelle affectation" });
  await form.getByLabel("Véhicule disponible").selectOption({ label: pair.fleetNumber });
  await form.getByLabel("Conducteur actif du même site").selectOption({ label: pair.driverOption });
  await form.getByRole("button", { name: "Affecter" }).click();
  const alert = form.getByRole("alert");
  await expect(alert).toContainText("L'affectation ne respecte pas les conditions d'éligibilité.");
  await expect(alert).toContainText("Catégorie de permis insuffisante");
});

test("un utilisateur d'une autre société ne voit aucune affectation de la première", async ({ page, request }) => {
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });
  const ops = await apiLogin(request, account("OPS_MANAGER", dispatcher.workspace));
  const vehicles = await (await request.get("/api/v1/vehicles", { headers: ops, params: { fleet_number: pair.fleetNumber } })).json();
  const drivers = await (await request.get("/api/v1/drivers", { headers: ops, params: { q: pair.driverOption.split(" — ")[1]! } })).json();
  const created = await request.post("/api/v1/vehicle-assignments", {
    headers: ops,
    data: {
      vehicle_id: vehicles.items[0].vehicle_id,
      driver_id: drivers.items[0].driver_id,
      valid_from: new Date().toISOString(),
    },
  });
  expect(created.status()).toBe(201);

  const other = accounts().find((a) => a.role === "OPS_MANAGER" && a.workspace !== dispatcher.workspace);
  expect(other, "le seed fictif crée deux sociétés").toBeTruthy();
  await uiLogin(page, other!);
  await page.goto("/affectations");
  await expect(page.getByRole("heading", { name: "Affectations conducteur ↔ véhicule" })).toBeVisible();
  await expect(page.getByText(pair.fleetNumber)).toHaveCount(0);
  const direct = await request.get(`/api/v1/vehicle-assignments/${(await created.json()).vehicle_assignment_id}`, {
    headers: await apiLogin(request, other!),
  });
  expect(direct.status()).toBe(404);
});
