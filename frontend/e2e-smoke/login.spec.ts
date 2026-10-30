import { expect, test } from "@playwright/test";

test("affiche la connexion et ses champs accessibles sans compte de test", async ({ page }) => {
  await page.goto("/connexion");

  await expect(page.getByRole("heading", { name: "MINEFLEET 360" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Code de l'espace de travail" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Adresse e-mail" })).toBeVisible();
  await expect(page.getByLabel("Mot de passe", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Mot de passe oublié ?" })).toBeVisible();
});

test("recharge le shell hors ligne sans mettre l'API en cache", async ({ page, request, context }) => {
  await page.goto("/connexion");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");

  const manifest = await request.get("/manifest.webmanifest");
  expect(manifest.ok()).toBeTruthy();
  expect((await manifest.json()).display).toBe("standalone");

  const worker = await request.get("/sw.js");
  expect(worker.ok()).toBeTruthy();
  const source = await worker.text();
  expect(source).toContain('url.pathname.startsWith("/api/")');

  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  // Un premier rechargement en ligne garantit que la page est contrôlée, même si clients.claim()
  // s'est produit entre la lecture de controller et l'abonnement à controllerchange.
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  await context.setOffline(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "MINEFLEET 360" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Mode hors ligne");
});
