import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, dispatcherSite, type Account } from "../e2e/fixtures";

/**
 * Signalement de panne sans réseau (phase 4) : coupure en cours de session, file IndexedDB réelle, rejeu
 * idempotent (Idempotency-Key) avec l'heure du constat ; réponse perdue sans doublon. Engin fictif propre au test.
 */
const performer = () => account("DISPATCHER");

async function freshVehicle(request: APIRequestContext): Promise<{ id: string; fleetNumber: string }> {
  const headers = await apiLogin(request, performer());
  const siteId = await dispatcherSite(request, headers);
  const admin = await apiLogin(request, account("TENANT_ADMIN", performer().workspace));
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: admin })).json();
  const category = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `E2E-PAN-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
  const created = await request.post("/api/v1/vehicles", {
    headers: admin,
    data: { site_id: siteId, vehicle_category_id: category.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(created.status()).toBe(201);
  return { id: (await created.json()).vehicle_id, fleetNumber };
}

async function workOrders(request: APIRequestContext, vehicleId: string): Promise<number> {
  const headers = await apiLogin(request, account("OPS_MANAGER", performer().workspace));
  const resp = await request.get("/api/v1/work-orders", { headers, params: { vehicle_id: vehicleId, open_only: "false" } });
  expect(resp.status()).toBe(200);
  return (await resp.json()).total as number;
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

/** Formulaire ouvert et engin choisi en ligne (liste des engins chargée avant la coupure). */
async function startReport(page: Page, fleetNumber: string): Promise<void> {
  await page.goto("/atelier");
  await page.getByRole("button", { name: "Signaler une panne" }).click();
  const vehicle = page.getByRole("combobox", { name: /^Véhicule/ });
  await expect(vehicle.locator("option", { hasText: fleetNumber })).toHaveCount(1);
  await vehicle.selectOption({ label: fleetNumber });
}

async function submitUntilClosed(page: Page): Promise<void> {
  const form = page.getByRole("form", { name: "Signaler une panne" });
  await page.getByRole("button", { name: "Enregistrer le signalement" }).click();
  try {
    await expect(form).toBeHidden({ timeout: 3_000 });
  } catch {
    await page.getByRole("button", { name: "Enregistrer le signalement" }).click();
    await expect(form).toBeHidden();
  }
}

test("panne signalée sans réseau, synchronisée une seule fois au retour du réseau", async ({ page, context, request }) => {
  const vehicle = await freshVehicle(request);
  await uiLogin(page, performer());
  await startReport(page, vehicle.fleetNumber);
  await page.getByLabel(/Panne bloquante/).check();
  await context.setOffline(true);
  await expect(page.getByText(/prévenez le répartiteur par radio/)).toBeVisible();
  await submitUntilClosed(page);
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText(new RegExp(`Signalement de panne — ${vehicle.fleetNumber}`))).toBeVisible();
  await expect(queue.getByText("En attente de synchronisation")).toBeVisible();
  expect(await workOrders(request, vehicle.id)).toBe(0);

  await context.setOffline(false);
  await expect(queue.getByText(/Synchronisé — OT-/)).toBeVisible({ timeout: 20_000 });
  expect(await workOrders(request, vehicle.id)).toBe(1);
  await page.reload();
  await expect(page.getByText(/Synchronisé — OT-/)).toBeVisible();
  expect(await workOrders(request, vehicle.id)).toBe(1);
});

test("réponse perdue : le signalement créé n'est pas dupliqué au rejeu", async ({ page, request }) => {
  const vehicle = await freshVehicle(request);
  await uiLogin(page, performer());
  let dropped = false;
  await page.route("**/api/v1/work-orders", async (route) => {
    if (route.request().method() === "POST" && !dropped) {
      dropped = true;
      await route.fetch(); // le serveur crée l'ordre de travail…
      await route.abort("connectionreset"); // …mais la réponse n'arrive jamais
      return;
    }
    await route.continue();
  });
  await startReport(page, vehicle.fleetNumber);
  await submitUntilClosed(page);
  await expect(page.getByText(/Synchronisé — OT-/)).toBeVisible({ timeout: 20_000 });
  expect(dropped).toBe(true);
  expect(await workOrders(request, vehicle.id)).toBe(1);
});
