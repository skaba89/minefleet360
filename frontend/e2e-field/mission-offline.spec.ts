import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, type Account } from "../e2e/fixtures";

/**
 * Avancement de mission sans réseau (phase 4, décisions du 18 novembre 2026) : étapes mises en file avec leur
 * heure réelle, état projeté à l'écran, synchronisation dans l'ordre, sans doublon (client_event_id).
 */
const dispatcher = () => account("DISPATCHER");

async function freshMission(request: APIRequestContext): Promise<string> {
  const d = dispatcher();
  const site = await dispatcherSite(request, await apiLogin(request, d));
  const admin = await apiLogin(request, account("TENANT_ADMIN", d.workspace));
  const ops = await apiLogin(request, account("OPS_MANAGER", d.workspace));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const places: Record<string, string> = {};
  for (const [code, kind] of [
    [`FO${suffix}`, "LOADING_POINT"],
    [`VE${suffix}`, "DUMP_POINT"],
  ] as const) {
    const resp = await request.post("/api/v1/site-locations", {
      headers: admin,
      data: { site_id: site, code, name: `Lieu ${code}`, kind },
    });
    expect(resp.status()).toBe(201);
    places[kind] = (await resp.json()).site_location_id;
  }
  const material = await request.post("/api/v1/materials", {
    headers: admin,
    data: { code: `BX${suffix}`, name: `Bauxite ${suffix}` },
  });
  expect(material.status()).toBe(201);
  const pair = await preparePair(request, d.workspace, site, { eligible: true });
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
  const mission = await request.post("/api/v1/missions", {
    headers: ops,
    data: {
      vehicle_assignment_id: (await assignment.json()).vehicle_assignment_id,
      origin_location_id: places.LOADING_POINT,
      destination_location_id: places.DUMP_POINT,
      material_id: (await material.json()).material_id,
      planned_start: new Date().toISOString(),
    },
  });
  expect(mission.status()).toBe(201);
  return (await mission.json()).mission_id;
}

async function missionState(request: APIRequestContext, id: string): Promise<{ status: string; departures: number }> {
  const headers = await apiLogin(request, account("OPS_MANAGER", dispatcher().workspace));
  const body = await (await request.get(`/api/v1/missions/${id}`, { headers })).json();
  return {
    status: body.status,
    departures: (body.events as { event_type: string }[]).filter((e) => e.event_type === "DEPARTED").length,
  };
}

/** Connexion valable aussi en profil téléphone (menu replié). */
async function uiLogin(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
}

test("étapes de mission saisies sans réseau, appliquées dans l'ordre au retour du réseau", async ({ page, context, request }) => {
  test.setTimeout(90_000);
  const id = await freshMission(request);
  await uiLogin(page, dispatcher());
  await page.goto(`/missions/${id}`);
  await expect(page.getByRole("button", { name: "Départ" })).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("button", { name: "Départ" }).click();
  // État projeté : l'étape suivante est proposée sans réseau.
  await page.getByRole("button", { name: "Arrivée au chargement" }).click();
  await expect(page.getByRole("button", { name: "Chargement terminé" })).toBeVisible();
  await expect(page.getByText(/2 étape\(s\) saisie\(s\) sur l'appareil/)).toBeVisible();
  expect((await missionState(request, id)).status).toBe("ASSIGNED");

  await context.setOffline(false);
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText(/Synchronisé — En chargement/)).toBeVisible({ timeout: 20_000 });
  await expect.poll(async () => (await missionState(request, id)).status, { timeout: 20_000 }).toBe("LOADING");
  expect((await missionState(request, id)).departures).toBe(1);
});

test("réponse perdue : l'étape déjà appliquée n'est pas dupliquée au rejeu", async ({ page, request }) => {
  test.setTimeout(90_000);
  const id = await freshMission(request);
  await uiLogin(page, dispatcher());
  let dropped = false;
  await page.route(`**/api/v1/missions/${id}/events`, async (route) => {
    if (route.request().method() === "POST" && !dropped) {
      dropped = true;
      await route.fetch(); // le serveur applique le départ…
      await route.abort("connectionreset"); // …mais la réponse n'arrive jamais
      return;
    }
    await route.continue();
  });
  await page.goto(`/missions/${id}`);
  await page.getByRole("button", { name: "Départ" }).click();
  await expect.poll(async () => (await missionState(request, id)).status, { timeout: 20_000 }).toBe("EN_ROUTE_EMPTY");
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText(/Synchronisé/)).toBeVisible({ timeout: 20_000 });
  expect(dropped).toBe(true);
  expect((await missionState(request, id)).departures).toBe(1);
});
