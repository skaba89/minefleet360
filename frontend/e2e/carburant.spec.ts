import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, preparePair, uiLogin } from "./fixtures";

// Authentification et autorisation effectives : la disparition d'un menu ne suffit pas
// pour protéger les API métier. Tous les utilisateurs sont issus du seed fictif.
test("le responsable des opérations peut consulter le module carburant", async ({ page, request }) => {
  const manager = account("OPS_MANAGER", "fictif-minier");
  const headers = await apiLogin(request, manager);
  const response = await request.get("/api/v1/fuel/tanks", { headers });
  expect(response.status(), await response.text()).toBe(200);
  const data = await response.json();
  expect(Array.isArray(data.items)).toBeTruthy();

  await uiLogin(page, manager);
  await page.getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Carburant" }).click();
  await expect(page).toHaveURL(/\/carburant$/);
});

test("un utilisateur RH ne peut pas consulter les stocks de carburant", async ({ page, request }) => {
  const hr = account("HR", "fictif-minier");
  const headers = await apiLogin(request, hr);
  const response = await request.get("/api/v1/fuel/tanks", { headers });
  expect(response.status()).toBe(403);

  await uiLogin(page, hr);
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Carburant" })).toHaveCount(0);
});

test("réception en cuve : le stock augmente et un doublon de référence est refusé", async ({ request }) => {
  const manager = account("OPS_MANAGER", "fictif-minier");
  const headers = await apiLogin(request, manager);
  const siteId = await dispatcherSite(
    request,
    await apiLogin(request, account("DISPATCHER", manager.workspace)),
  );

  const suffix = Math.random().toString(36).slice(2, 10).toUpperCase();
  const tank = await request.post("/api/v1/fuel/tanks", {
    headers,
    data: { site_id: siteId, code: `E2E-${suffix}`, fuel_type: "DIESEL", capacity_liters: 1000 },
  });
  expect(tank.status(), await tank.text()).toBe(201);
  const created = await tank.json();
  expect(Number(created.balance_liters)).toBe(0);

  const receipt = {
    liters: 350,
    reference: `BL-${suffix}`,
    occurred_at: new Date().toISOString(),
  };
  const path = `/api/v1/fuel/tanks/${created.fuel_tank_id}/receipts`;
  const first = await request.post(path, { headers, data: receipt });
  expect(first.status(), await first.text()).toBe(201);

  const rows = await request.get("/api/v1/fuel/tanks", { headers, params: { site_id: siteId } });
  expect(rows.status()).toBe(200);
  const updated = (await rows.json()).items.find(
    (item: { fuel_tank_id: string }) => item.fuel_tank_id === created.fuel_tank_id,
  );
  expect(updated).toBeTruthy();
  expect(Number(updated.balance_liters)).toBe(350);
  expect(Number(updated.available_liters)).toBe(350);

  const duplicate = await request.post(path, { headers, data: receipt });
  expect(duplicate.status()).toBe(409);
});

test("ravitaillement : réservation, double validation et sortie de stock", async ({ request }) => {
  const workspace = "fictif-minier";
  const manager = await apiLogin(request, account("OPS_MANAGER", workspace));
  const approver = await apiLogin(request, account("TENANT_ADMIN", workspace));
  const siteId = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", workspace)));
  const pair = await preparePair(request, workspace, siteId, { eligible: true });
  const vehiclesResponse = await request.get("/api/v1/vehicles", { headers: manager, params: { fleet_number: pair.fleetNumber } });
  expect(vehiclesResponse.status()).toBe(200);
  const vehicle = (await vehiclesResponse.json()).items[0];
  const driversResponse = await request.get("/api/v1/drivers", { headers: manager, params: { q: pair.driverOption.split(" — ")[1]! } });
  expect(driversResponse.status()).toBe(200);
  const driver = (await driversResponse.json()).items[0];
  const assignment = await request.post("/api/v1/vehicle-assignments", {
    headers: manager,
    data: { vehicle_id: vehicle.vehicle_id, driver_id: driver.driver_id, valid_from: new Date().toISOString() },
  });
  expect(assignment.status(), await assignment.text()).toBe(201);

  const suffix = Math.random().toString(36).slice(2, 9).toUpperCase();
  const tankResponse = await request.post("/api/v1/fuel/tanks", {
    headers: manager,
    data: { site_id: siteId, code: `RAV-${suffix}`, fuel_type: "DIESEL", capacity_liters: 500 },
  });
  expect(tankResponse.status(), await tankResponse.text()).toBe(201);
  const tankId = (await tankResponse.json()).fuel_tank_id;
  const receipt = await request.post(`/api/v1/fuel/tanks/${tankId}/receipts`, {
    headers: manager,
    data: { liters: 300, reference: `BL-${suffix}`, occurred_at: new Date().toISOString() },
  });
  expect(receipt.status(), await receipt.text()).toBe(201);

  const categoryResponse = await request.get("/api/v1/vehicle-categories", { headers: manager });
  expect(categoryResponse.status()).toBe(200);
  const category = (await categoryResponse.json()).find(
    (item: { vehicle_category_id: string }) => item.vehicle_category_id === vehicle.vehicle_category_id,
  );
  expect(category).toBeTruthy();
  const meter_kind = category.has_hour_meter ? "HOUR_METER" : category.has_odometer ? "ODOMETER" : null;
  const issueResponse = await request.post("/api/v1/fuel/issues", {
    headers: manager,
    data: {
      fuel_tank_id: tankId,
      vehicle_id: vehicle.vehicle_id,
      driver_id: driver.driver_id,
      liters: 60,
      meter_kind,
      meter_value: meter_kind ? 1200 : null,
      requested_at: new Date().toISOString(),
    },
  });
  expect(issueResponse.status(), await issueResponse.text()).toBe(201);
  const issueId = (await issueResponse.json()).fuel_issue_id;
  const tanksUrl = "/api/v1/fuel/tanks";
  const getTank = async () => {
    const response = await request.get(tanksUrl, { headers: manager, params: { site_id: siteId } });
    expect(response.status()).toBe(200);
    return (await response.json()).items.find((item: { fuel_tank_id: string }) => item.fuel_tank_id === tankId);
  };
  const pending = await getTank();
  expect(Number(pending.balance_liters)).toBe(300);
  expect(Number(pending.reserved_liters)).toBe(60);
  expect(Number(pending.available_liters)).toBe(240);

  const decisionPath = `/api/v1/fuel/issues/${issueId}/decision`;
  const selfApproval = await request.post(decisionPath, { headers: manager, data: { decision: "APPROVED" } });
  expect(selfApproval.status()).toBe(409);
  const approval = await request.post(decisionPath, { headers: approver, data: { decision: "APPROVED" } });
  expect(approval.status(), await approval.text()).toBe(200);
  expect((await approval.json()).status).toBe("APPROVED");

  const completed = await getTank();
  expect(Number(completed.balance_liters)).toBe(240);
  expect(Number(completed.reserved_liters)).toBe(0);
  expect(Number(completed.available_liters)).toBe(240);
});

test("inventaire physique : correction de stock journalisée et dépassement refusé", async ({ request }) => {
  const workspace = "fictif-minier";
  const manager = await apiLogin(request, account("OPS_MANAGER", workspace));
  const siteId = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", workspace)));
  const suffix = Math.random().toString(36).slice(2, 10).toUpperCase();
  const tankResponse = await request.post("/api/v1/fuel/tanks", {
    headers: manager,
    data: { site_id: siteId, code: `INV-${suffix}`, fuel_type: "DIESEL", capacity_liters: 500 },
  });
  expect(tankResponse.status(), await tankResponse.text()).toBe(201);
  const tankId = (await tankResponse.json()).fuel_tank_id;
  const receipt = await request.post(`/api/v1/fuel/tanks/${tankId}/receipts`, {
    headers: manager,
    data: { liters: 300, reference: `BL-${suffix}`, occurred_at: new Date().toISOString() },
  });
  expect(receipt.status(), await receipt.text()).toBe(201);

  const path = `/api/v1/fuel/tanks/${tankId}/stocktakes`;
  const stocktake = await request.post(path, {
    headers: manager,
    data: {
      counted_liters: 285,
      reference: `INV-${suffix}`,
      reason_code: "MEASUREMENT",
      occurred_at: new Date().toISOString(),
    },
  });
  expect(stocktake.status(), await stocktake.text()).toBe(201);
  const record = await stocktake.json();
  expect(Number(record.expected_liters)).toBe(300);
  expect(Number(record.counted_liters)).toBe(285);
  expect(Number(record.delta_liters)).toBe(-15);

  const rows = await request.get("/api/v1/fuel/tanks", { headers: manager, params: { site_id: siteId } });
  expect(rows.status()).toBe(200);
  const updated = (await rows.json()).items.find(
    (item: { fuel_tank_id: string }) => item.fuel_tank_id === tankId,
  );
  expect(Number(updated.balance_liters)).toBe(285);
  expect(Number(updated.available_liters)).toBe(285);

  const history = await request.get("/api/v1/fuel/stocktakes", { headers: manager, params: { site_id: siteId } });
  expect(history.status()).toBe(200);
  expect((await history.json()).items.some(
    (item: { fuel_stocktake_id: string }) => item.fuel_stocktake_id === record.fuel_stocktake_id,
  )).toBeTruthy();

  const invalid = await request.post(path, {
    headers: manager,
    data: {
      counted_liters: 501,
      reference: `INV-ERR-${suffix}`,
      reason_code: "MEASUREMENT",
      occurred_at: new Date().toISOString(),
    },
  });
  expect(invalid.status()).toBe(409);
});
