import { expect, test } from "@playwright/test";

import { account, totpCode } from "./fixtures";

// Double authentification (C-03) par l'interface : activation volontaire, connexion en deux étapes,
// codes de récupération, puis désactivation pour rendre le compte fictif dans son état initial.

test("activer la double authentification puis se connecter avec un code", async ({ page }) => {
  test.setTimeout(90_000); // attente d'un pas TOTP (30 s) avant la désactivation
  // Rôle facultatif et compte utilisé par aucun autre test (les fichiers E2E tournent en parallèle).
  const user = account("WORKSHOP_CHIEF");
  const login = async () => {
    await page.goto("/connexion");
    await page.getByLabel("Code de l'espace de travail").fill(user.workspace);
    await page.getByLabel("Adresse e-mail").fill(user.email);
    await page.getByLabel("Mot de passe").fill(user.password);
    await page.getByRole("button", { name: "Se connecter" }).click();
  };

  await login();
  await page.getByRole("link", { name: "Sécurité" }).click();
  await page.getByRole("button", { name: "Commencer" }).click();
  const secret = (await page.locator(".secret code").innerText()).replace(/\s/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await page.getByLabel(/code à 6 chiffres/).fill(totpCode(secret));
  await page.getByRole("button", { name: "Activer" }).click();
  const codes = page.getByRole("region", { name: "Codes de récupération" }).locator("code");
  await expect(codes).toHaveCount(10);
  await page.getByRole("button", { name: "J'ai conservé mes codes" }).click();
  await expect(page.getByRole("status")).toContainText("Double authentification active");

  // Nouvelle connexion : le mot de passe seul ne suffit plus.
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await login();
  await expect(page.getByLabel("Code de vérification")).toBeVisible();
  await page.getByLabel("Code de vérification").fill("000000");
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(page.getByRole("alert")).toContainText("Code de vérification invalide");
  await page.getByLabel("Code de vérification").fill(totpCode(secret, 30)); // pas suivant, jamais utilisé
  await page.getByRole("button", { name: "Valider le code" }).click();
  await expect(page.getByRole("heading", { name: /^Bonjour/ })).toBeVisible();

  // Désactivation (rôle facultatif) : mot de passe + code d'un pas encore inutilisé.
  await page.getByRole("link", { name: "Sécurité" }).click();
  await page.getByRole("button", { name: "Désactiver" }).click();
  const form = page.getByRole("form", { name: "Désactiver la double authentification" });
  await form.getByLabel("Mot de passe").fill(user.password);
  await page.waitForTimeout(31_000); // le pas utilisé à la connexion ne peut pas être rejoué
  await form.getByLabel("Code actuel de l'application").fill(totpCode(secret, 30));
  await form.getByRole("button", { name: "Désactiver" }).click();
  await expect(page.getByRole("button", { name: "Commencer" })).toBeVisible();
});
