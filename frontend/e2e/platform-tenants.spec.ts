import { expect, test } from "@playwright/test";

import { uiPlatformLogin } from "./fixtures";

// Écart recette UI : parcours plateforme — création d'une société cliente, suspension, réactivation.

test("parcours plateforme : créer, suspendre puis réactiver une société cliente", async ({ page }) => {
  test.setTimeout(120_000);
  const suffix = Math.random().toString(36).slice(2, 7).toLowerCase();
  const code = `e2e-soc-${suffix}`;
  const displayName = `Société E2E ${suffix.toUpperCase()}`;

  await uiPlatformLogin(page);
  await page.goto("/plateforme/nouvelle-societe");
  const form = page.getByRole("form", { name: "Informations de la société" });
  await form.getByLabel("Code unique (minuscules et tirets)").fill(code);
  await form.getByLabel("Raison sociale").fill(`${displayName} SARL fictive`);
  await form.getByLabel("Nom affiché").fill(displayName);
  await form.getByLabel("E-mail du premier administrateur").fill(`admin.e2e.${suffix}@exemple.mf`);
  await form.getByLabel("Nom du premier administrateur").fill("Admin E2E Fictif");
  await form.getByRole("button", { name: "Créer et inviter" }).click();

  // La liste des sociétés montre la nouvelle société active, hors démonstration.
  await expect(page).toHaveURL(/\/plateforme\/societes$/);
  const row = page.getByRole("row", { name: new RegExp(code) });
  await expect(row).toContainText("Active");
  await expect(row).toContainText("Hors démonstration");

  // Suspension motivée (les sessions de la société sont révoquées côté serveur).
  await row.getByRole("button", { name: "Suspendre" }).click();
  const suspendHeading = page.getByRole("heading", { name: `Suspendre ${displayName}` });
  await expect(suspendHeading).toBeVisible();
  await page.getByLabel("Motif obligatoire").fill("Suspension planifiée dans le cadre du test de recette E2E.");
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(row).toContainText("Suspendue");

  // Réactivation.
  await row.getByRole("button", { name: "Réactiver" }).click();
  await expect(page.getByRole("heading", { name: `Réactiver ${displayName}` })).toBeVisible();
  await page.getByLabel("Motif obligatoire").fill("Réactivation après contrôle du test de recette E2E.");
  await page.getByRole("button", { name: "Confirmer" }).click();
  await expect(row).toContainText("Active");
});
