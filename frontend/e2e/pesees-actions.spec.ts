import { expect, test, type APIRequestContext } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Écart recette UI : correction et annulation d'une pesée valide (dispatch.weighing.correct).

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

test("pesée valide : corrigée puis annulée par l'OPS_MANAGER, traces visibles", async ({ page, request }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER");
  const dispatcherHeaders = await apiLogin(request, dispatcher);
  const site = await dispatcherSite(request, dispatcherHeaders);
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const admin = await apiLogin(request, account("TENANT_ADMIN", dispatcher.workspace));
  const place = (code: string, kind: string) =>
    post(request, "/api/v1/site-locations", admin, { site_id: site, code, name: `Lieu ${code}`, kind });
  const origin = await place(`FOS${suffix}`, "LOADING_POINT");
  const destination = await place(`VER${suffix}`, "DUMP_POINT");
  const bridge = await place(`PONT${suffix}`, "WEIGHBRIDGE");
  const material = await post(request, "/api/v1/materials", admin, { code: `CA${suffix}`, name: `Clinker ${suffix}` });

  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });
  const opsAccount = account("OPS_MANAGER", dispatcher.workspace);
  const ops = await apiLogin(request, opsAccount);
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
  const detail = await (await request.get(url, { headers: ops })).json();
  const ticket = await post(request, "/api/v1/weighing-tickets", ops, {
    rotation_id: detail.rotations[0].rotation_id,
    weighbridge_location_id: bridge.site_location_id,
    ticket_number: `W-${suffix}`,
    source: "WEIGHBRIDGE",
    weighed_at: new Date().toISOString(),
    gross_kg: 52_000,
    tare_kg: 18_000,
  });
  expect(ticket.status).toBe("VALID");

  await uiLogin(page, opsAccount);
  await page.goto("/pesees");
  const original = page.getByRole("row", { name: new RegExp(`W-${suffix}`) });
  await expect(original).toContainText("Valide");
  await expect(original).toContainText("34,00");

  // 1. Correction : nouveau ticket qui remplace l'ancien, motif tracé.
  await original.getByRole("button", { name: "Corriger" }).click();
  const correction = page.getByRole("form", { name: `Corriger la pesée W-${suffix}` });
  await correction.getByLabel("Poids brut (kg)").fill("55000");
  await correction.getByLabel("Motif de la correction").selectOption("ENTRY_ERROR");
  await correction.getByRole("button", { name: "Enregistrer la correction" }).click();
  const corrected = page.getByRole("row", { name: new RegExp(`W-${suffix}`) }).filter({ hasText: "Corrige une pesée annulée" });
  await expect(corrected).toContainText("Valide");
  await expect(corrected).toContainText("37,00");
  await expect(
    page.getByRole("row", { name: new RegExp(`W-${suffix}`) }).filter({ hasNotText: "Corrige une pesée annulée" }),
  ).toContainText("Annulée");

  // 2. Annulation de la pesée corrigée : motif conservé, rien n'est effacé.
  await corrected.getByRole("button", { name: "Annuler", exact: true }).click();
  const cancellation = page.getByRole("form", { name: `Annuler la pesée W-${suffix}` });
  await cancellation.getByLabel("Motif").selectOption("DUPLICATE");
  await cancellation.getByRole("button", { name: "Annuler la pesée" }).click();
  await expect(corrected).toContainText("Annulée");
});
