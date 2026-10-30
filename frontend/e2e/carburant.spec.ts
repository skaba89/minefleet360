import { expect, test } from "@playwright/test";

import { account, apiLogin, uiLogin } from "./fixtures";

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
  const meResponse = await request.get("/api/v1/me", { headers });
  expect(meResponse.status()).toBe(200);
  const me = await meResponse.json();
  const siteId = me.grants.find((g: { scope_type: string; site_id: string | null }) => g.scope_type === "SITE")?.site_id;
  expect(siteId, "le compte doit être affecté à un site").toBeTruthy();

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
