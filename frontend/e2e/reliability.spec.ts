import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : fiabilité du parc (/atelier/fiabilite) — un OT immobilisant, clôturé avec
// main-d'œuvre, doit alimenter les indicateurs (pannes, disponibilité, MTTR) et rester visible
// au changement de période ; les rôles sans `maintenance.reliability.read` se voient refuser la page.
// Le flux OT est préparé par l'API (le parcours d'atelier complet est couvert par atelier.spec.ts).
const WORKSPACE = "fictif-transport";

test("fiabilité du parc : OT clôturé alimente les indicateurs, période 30 jours, refus sinon", async ({ page, request, browser }) => {
  test.setTimeout(120_000);
  const ops = account("OPS_MANAGER", WORKSPACE);
  const opsHeaders = await apiLogin(request, ops);
  const chiefHeaders = await apiLogin(request, account("WORKSHOP_CHIEF", WORKSPACE));
  const dispatcherHeaders = await apiLogin(request, account("DISPATCHER", WORKSPACE));
  const site = await dispatcherSite(request, dispatcherHeaders);
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: opsHeaders })).json();
  const truck = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `FIA-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
  const vehicle = await request.post("/api/v1/vehicles", {
    headers: opsHeaders,
    data: { site_id: site, vehicle_category_id: truck.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(vehicle.status(), await vehicle.text()).toBe(201);
  const vehicleId = (await vehicle.json()).vehicle_id;

  // OT immobilisant : signalement → approbation → auto-assignation → démarrage → 120 min
  // de main-d'œuvre → travaux terminés → contrôle qualité par une autre personne.
  const order = await request.post("/api/v1/work-orders", {
    headers: dispatcherHeaders,
    data: { vehicle_id: vehicleId, symptom_code: "ENGINE", priority: "HIGH", immobilize: true },
  });
  expect(order.status(), await order.text()).toBe(201);
  const orderId = (await order.json()).work_order_id;
  const me = await (await request.get("/api/v1/me", { headers: chiefHeaders })).json();
  async function transition(kind: string, headers: Record<string, string>, body: Record<string, unknown> = {}) {
    const current = await request.get(`/api/v1/work-orders/${orderId}`, { headers });
    const etag = current.headers()["etag"] ?? "";
    const resp = await request.post(`/api/v1/work-orders/${orderId}/${kind}`, { headers: { ...headers, "If-Match": etag }, data: body });
    expect(resp.status(), await resp.text()).toBe(200);
    return resp;
  }
  await transition("decision", chiefHeaders, { action: "APPROVE" });
  await transition("decision", chiefHeaders, { action: "ASSIGN", assigned_to: me.user_account_id });
  await transition("progress", chiefHeaders, { action: "START" });
  const labour = await request.post(`/api/v1/work-orders/${orderId}/labour`, {
    headers: chiefHeaders,
    data: { minutes: 120, performed_on: new Date().toISOString().slice(0, 10) },
  });
  expect(labour.status(), await labour.text()).toBe(201);
  await transition("progress", chiefHeaders, { action: "SUBMIT", work_done: "Remplacement fictif (E2E fiabilité)" });
  await transition("decision", opsHeaders, { action: "QC_PASS" });

  // Lecture : les indicateurs du parc incluent l'engin (panne, immobilisation, main-d'œuvre).
  await uiLogin(page, account("WORKSHOP_CHIEF", WORKSPACE));
  await page.goto("/atelier/fiabilite");
  await expect(page.getByRole("heading", { level: 1, name: "Fiabilité du parc" })).toBeVisible();
  const synthesis = page.locator("dl[aria-label='Synthèse du parc']");
  await expect(synthesis).toContainText("MTBF moyen");
  const row = page.getByRole("row", { name: new RegExp(fleetNumber) });
  await expect(row).toBeVisible();
  await expect(row.locator("td").nth(2)).toHaveText("1"); // une panne immobilisante sur la période
  await expect(row.locator("td").nth(6)).toContainText("2 h"); // 120 minutes de main-d'œuvre

  // Le changement de période conserve l'engin (l'OT date d'aujourd'hui).
  await page.getByLabel("Période").selectOption({ label: "30 jours" });
  await expect(row).toBeVisible();

  // Un rôle sans `maintenance.reliability.read` se voit refuser la page (formulaire canonique).
  const dispatcherContext = await browser.newContext();
  const dispatcherPage = await dispatcherContext.newPage();
  await uiLogin(dispatcherPage, account("DISPATCHER", WORKSPACE));
  await dispatcherPage.goto("/atelier/fiabilite");
  await expect(dispatcherPage.getByRole("alert")).toContainText("Vous n'avez pas accès à cette page.");
  await dispatcherContext.close();
});
