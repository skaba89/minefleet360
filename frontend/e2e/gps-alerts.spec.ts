import { expect, test, type APIRequestContext } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Écart recette UI : alerte GPS (excès de vitesse) ouverte par la télémétrie, prise en compte depuis l'UI.

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

test("alerte d'excès de vitesse : ingestion traceur, prise en compte, re-prise refusée", async ({ page, request }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const opsAccount = account("OPS_MANAGER", dispatcher.workspace);
  const ops = await apiLogin(request, opsAccount);

  // Véhicule sur le site, politique de vitesse à 50 km/h, traceur provisionné.
  const pair = await preparePair(request, dispatcher.workspace, site, { eligible: true });
  const vehicle = (
    await (await request.get("/api/v1/vehicles", { headers: ops, params: { fleet_number: pair.fleetNumber } })).json()
  ).items[0];
  const policy = await request.put(`/api/v1/sites/${site}/gps-policy`, { headers: ops, data: { speed_limit_kmh: 50 } });
  expect(policy.ok(), await policy.text()).toBeTruthy();
  const tracker = await post(request, `/api/v1/vehicles/${vehicle.vehicle_id}/gps/tracker`, ops, {
    device_id: `TRK-E2E-${suffix}`,
  });
  expect(tracker.token).toMatch(/^gps_/);

  // Ingestion traceur (authentification machine) : un seul point au-dessus de la limite suffit.
  const ingest = await request.post("/api/v1/gps/telemetry", {
    headers: { Authorization: `Bearer ${tracker.token}` },
    data: {
      device_id: `TRK-E2E-${suffix}`,
      latitude: 10.4321,
      longitude: -12.7654,
      recorded_at: new Date().toISOString(),
      sequence: 1,
      speed_kmh: 80,
    },
  });
  expect(ingest.status(), await ingest.text()).toBe(204);

  // L'alerte OVERSPEED apparaît côté API avant d'être visible dans l'UI.
  let alertId: string | undefined;
  await expect(async () => {
    const alerts = await (
      await request.get("/api/v1/gps/alerts", { headers: ops, params: { site_id: site, unacknowledged: "true" } })
    ).json();
    const found = alerts.items.find((a: { fleet_number: string }) => a.fleet_number === pair.fleetNumber);
    expect(found, "alerte OVERSPEED absente après ingestion").toBeTruthy();
    alertId = found.gps_alert_id;
  }).toPass({ timeout: 20_000 });

  // 1. L'OPS_MANAGER prend l'alerte en compte avec une remarque (invite navigateur).
  await uiLogin(page, opsAccount);
  await page.goto("/flotte-gps/alertes");
  const pendingRow = page.getByRole("row", { name: new RegExp(pair.fleetNumber) });
  await expect(pendingRow).toContainText("Excès de vitesse");
  page.on("dialog", (dialog) => void dialog.accept("Conducteur rappelé (E2E)."));
  await pendingRow.getByRole("button", { name: "Prendre en compte" }).click();
  await expect(page.getByText("Aucune alerte.")).toBeVisible();

  // 2. La liste complète montre la prise en compte horodatée avec la remarque.
  await page.getByLabel("Seulement les alertes non prises en compte").uncheck();
  const ackRow = page.getByRole("row", { name: new RegExp(pair.fleetNumber) });
  await expect(ackRow).toContainText("Conducteur rappelé (E2E).");

  // 3. Le serveur refuse une seconde prise en compte (409), sans nouveau prompt.
  const replay = await request.post(`/api/v1/gps/alerts/${alertId}/acknowledge`, {
    headers: ops,
    data: { note: "rejeu" },
  });
  expect(replay.status()).toBe(409);
});
