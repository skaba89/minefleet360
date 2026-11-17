import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, dispatcherSite, type Account } from "../e2e/fixtures";

/**
 * Relevé de compteur sans réseau (phase 4) : coupure en cours de session, file IndexedDB réelle, rejeu idempotent
 * (Idempotency-Key) acquitté par le serveur ; réponse perdue sans doublon. Engin fictif propre au test.
 */
const performer = () => account("DISPATCHER");

async function freshVehicle(request: APIRequestContext): Promise<{ id: string; fleetNumber: string }> {
  const headers = await apiLogin(request, performer());
  const siteId = await dispatcherSite(request, headers);
  const admin = await apiLogin(request, account("TENANT_ADMIN", performer().workspace));
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: admin })).json();
  const category = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `E2E-REL-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
  const created = await request.post("/api/v1/vehicles", {
    headers: admin,
    data: { site_id: siteId, vehicle_category_id: category.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(created.status()).toBe(201);
  return { id: (await created.json()).vehicle_id, fleetNumber };
}

/** Connexion valable aussi en profil téléphone (menu replié) : le bouton de déconnexion prouve la session. */
async function uiLogin(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
}

async function readings(request: APIRequestContext, vehicleId: string): Promise<number> {
  const headers = await apiLogin(request, performer());
  const resp = await request.get(`/api/v1/vehicles/${vehicleId}/meter-readings`, { headers });
  expect(resp.status()).toBe(200);
  return (await resp.json()).total as number;
}

async function openReadingForm(page: Page, vehicleId: string): Promise<void> {
  await page.goto(`/vehicules/${vehicleId}`);
  await expect(page.getByRole("heading", { name: "Compteurs" })).toBeVisible();
  await page.getByRole("button", { name: "Nouveau relevé" }).click();
  await page.getByLabel("Valeur relevée").fill("1000");
}

/** Le clic peut tomber pendant une re-renderisation : la fermeture du formulaire prouve la prise en compte. */
async function submitUntilClosed(page: Page): Promise<void> {
  const form = page.getByRole("form", { name: /Nouveau relevé de compteur/ });
  await page.getByRole("button", { name: "Enregistrer le relevé" }).click();
  try {
    await expect(form).toBeHidden({ timeout: 3_000 });
  } catch {
    await page.getByRole("button", { name: "Enregistrer le relevé" }).click();
    await expect(form).toBeHidden();
  }
}

test("relevé sans réseau, synchronisé une seule fois au retour du réseau", async ({ page, context, request }) => {
  const vehicle = await freshVehicle(request);
  await uiLogin(page, performer());
  await openReadingForm(page, vehicle.id);
  await context.setOffline(true);
  await submitUntilClosed(page);
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText(new RegExp(`Relevé de compteur — ${vehicle.fleetNumber}`))).toBeVisible();
  await expect(queue.getByText("En attente de synchronisation")).toBeVisible();
  expect(await readings(request, vehicle.id)).toBe(0);

  await context.setOffline(false);
  await expect(queue.getByText(/Synchronisé/)).toBeVisible({ timeout: 20_000 });
  expect(await readings(request, vehicle.id)).toBe(1);
  await page.reload();
  await expect(page.getByText(/Synchronisé/)).toBeVisible();
  expect(await readings(request, vehicle.id)).toBe(1);
});

test("réponse perdue : le relevé créé n'est pas dupliqué au rejeu", async ({ page, request }) => {
  const vehicle = await freshVehicle(request);
  await uiLogin(page, performer());
  let dropped = false;
  await page.route(`**/api/v1/vehicles/${vehicle.id}/meter-readings`, async (route) => {
    if (route.request().method() === "POST" && !dropped) {
      dropped = true;
      await route.fetch(); // le serveur crée le relevé…
      await route.abort("connectionreset"); // …mais la réponse n'arrive jamais
      return;
    }
    await route.continue();
  });
  await openReadingForm(page, vehicle.id);
  await submitUntilClosed(page);
  await expect(page.getByText(/Synchronisé/)).toBeVisible({ timeout: 20_000 });
  expect(dropped).toBe(true);
  expect(await readings(request, vehicle.id)).toBe(1);
});
