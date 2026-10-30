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
