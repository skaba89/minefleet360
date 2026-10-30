import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

test("anomalie de pompe : prise en charge, justification, clôture indépendante et isolation", async ({ page, request }) => {
  const workspace = "fictif-minier";
  const manager = account("OPS_MANAGER", workspace);
  const creator = account("TENANT_ADMIN", workspace);
  const outsider = account("TENANT_ADMIN", "fictif-transport");
  const managerHeaders = await apiLogin(request, manager);
  const creatorHeaders = await apiLogin(request, creator);
  const outsiderHeaders = await apiLogin(request, outsider);
  const siteId = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", workspace)));
  const suffix = Math.random().toString(36).slice(2, 10).toUpperCase();

  const tank = await request.post("/api/v1/fuel/tanks", {
    headers: creatorHeaders,
    data: { site_id: siteId, code: `AT-${suffix}`, fuel_type: "DIESEL", capacity_liters: 5000 },
  });
  expect(tank.status(), await tank.text()).toBe(201);
  const pump = await request.post("/api/v1/fuel/pumps", {
    headers: creatorHeaders,
    data: { fuel_tank_id: (await tank.json()).fuel_tank_id, code: `AP-${suffix}`, name: "Pompe anomalie E2E" },
  });
  expect(pump.status(), await pump.text()).toBe(201);
  const pumpId = (await pump.json()).fuel_pump_id;
  const readingIds: string[] = [];
  for (const [index, liters] of [100, 150].entries()) {
    const reading = await request.post(`/api/v1/fuel/pumps/${pumpId}/meter-readings`, {
      headers: creatorHeaders,
      data: {
        cumulative_liters: liters,
        measured_at: new Date(Date.now() - (10 - index * 5) * 60_000).toISOString(),
        source: "MANUAL",
        source_reference: `E2E-${suffix}-${index}`,
      },
    });
    expect(reading.status(), await reading.text()).toBe(201);
    readingIds.push((await reading.json()).fuel_pump_meter_reading_id);
  }
  const opened = await request.post(`/api/v1/fuel/pumps/${pumpId}/anomaly-cases`, {
    headers: creatorHeaders,
    data: { start_reading_id: readingIds[0], end_reading_id: readingIds[1] },
  });
  expect(opened.status(), await opened.text()).toBe(201);
  const caseId = (await opened.json()).fuel_pump_anomaly_case_id;
  const eventUrl = `/api/v1/fuel/anomaly-cases/${caseId}/events`;
  const foreignRead = await request.get(eventUrl, { headers: outsiderHeaders });
  expect(foreignRead.status()).toBe(404);

  await uiLogin(page, manager);
  await page.getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Carburant" }).click();
  const section = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Dossiers d’anomalies des pompes" }) });
  const row = section.getByRole("row").filter({ hasText: `AP-${suffix}` });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Consulter" }).click();

  for (const [button, justification, status] of [
    ["Prendre en charge", "Anomalie prise en charge E2E", "ACKNOWLEDGED"],
    ["Justifier", "Écart vérifié et documenté E2E", "JUSTIFIED"],
    ["Clôturer", "Contrôle terminé par un autre responsable E2E", "CLOSED"],
  ] as const) {
    await section.getByRole("form", { name: "Traiter une anomalie" }).getByRole("textbox", { name: "Justification" }).fill(justification);
    await section.getByRole("button", { name: button, exact: true }).click();
    await expect(section.getByRole("cell", { name: status, exact: true })).toBeVisible();
  }
  await expect(section.getByRole("form", { name: "Traiter une anomalie" })).toHaveCount(0);

  const history = await request.get(eventUrl, { headers: managerHeaders });
  expect(history.status()).toBe(200);
  expect((await history.json()).items.map((event: { event_type: string }) => event.event_type)).toEqual([
    "ACKNOWLEDGED", "JUSTIFIED", "CLOSED",
  ]);
});
