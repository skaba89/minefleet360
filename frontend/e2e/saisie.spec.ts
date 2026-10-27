import { expect, test } from "@playwright/test";

import { account, uiLogin } from "./fixtures";

// Saisie du parc et du personnel par l'interface (sans passer par l'API) puis affectation du résultat.
// Données fictives uniques à chaque exécution.

test("parc : créer un véhicule, l'immobiliser puis le remettre disponible", async ({ page }) => {
  const admin = account("TENANT_ADMIN");
  const fleetNumber = `UI-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
  await uiLogin(page, admin);
  await page.goto("/vehicules");
  await page.getByRole("button", { name: "Nouveau véhicule" }).click();
  const form = page.getByRole("form", { name: "Nouveau véhicule" });
  await form.getByLabel("Site").selectOption({ index: 1 });
  await form.getByLabel("Catégorie").selectOption({ label: "Camion-benne rigide (tombereau)" });
  await form.getByLabel("N° de parc (unique, définitif)").fill(fleetNumber);
  await form.getByLabel("Immatriculation").fill(`RC-${fleetNumber}`);
  await form.getByRole("button", { name: "Créer le véhicule" }).click();

  await expect(page.getByRole("heading", { name: new RegExp(fleetNumber) })).toContainText("Disponible");
  await page.getByRole("button", { name: "Changer le statut" }).click();
  const status = page.getByRole("form", { name: "Changer le statut" });
  await status.getByLabel("Nouveau statut").selectOption({ label: "Immobilisé" });
  await status.getByLabel(/Motif/).selectOption({ label: "Panne" });
  await status.getByRole("button", { name: "Valider le statut" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(fleetNumber) })).toContainText("Immobilisé");
  await expect(page.getByText("Panne").first()).toBeVisible();

  await page.getByRole("button", { name: "Changer le statut" }).click();
  await page.getByLabel("Nouveau statut").selectOption({ label: "Disponible" });
  await page.getByRole("button", { name: "Valider le statut" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(fleetNumber) })).toContainText("Disponible");
  await expect(page.getByRole("row", { name: /Immobilisé → Disponible/ })).toBeVisible();
});

test("personnel : créer un conducteur avec permis et habilitation, il devient affectable", async ({ page }) => {
  const hr = account("HR");
  const suffix = Math.random().toString(36).slice(2, 8).toUpperCase();
  await uiLogin(page, hr);
  await page.goto("/conducteurs");
  await page.getByRole("button", { name: "Nouveau conducteur" }).click();
  const form = page.getByRole("form", { name: "Nouveau conducteur" });
  await form.getByLabel("Site de rattachement").selectOption({ index: 1 });
  await form.getByLabel("Matricule (unique)").fill(`M-UI-${suffix}`);
  await form.getByLabel("Nom", { exact: true }).fill(`Nom-UI-${suffix}`);
  await form.getByLabel("Prénom").fill("Test");
  await form.getByLabel("Téléphone (+224…)").fill("+224000000999");
  await form.getByRole("button", { name: "Créer le conducteur" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`NOM-UI-${suffix}`) })).toContainText("Actif");

  await page.getByRole("button", { name: "Ajouter un permis" }).click();
  const lic = page.getByRole("form", { name: "Ajouter un permis" });
  await lic.getByLabel(/N° de permis/).fill(`PERMIS-FICTIF-UI-${suffix}`);
  await lic.getByLabel("Catégorie").selectOption("C");
  await lic.getByLabel("Délivré le").fill("2020-01-01");
  await lic.getByLabel("Expire le (inclus)").fill("2035-01-01");
  await lic.getByRole("button", { name: "Enregistrer le permis" }).click();
  await expect(page.getByRole("row", { name: /PERMIS-FICTIF-UI/ })).toContainText("Valide");

  await page.getByRole("button", { name: "Ajouter une habilitation" }).click();
  const qual = page.getByRole("form", { name: "Ajouter une habilitation" });
  await qual.getByLabel(/Catégorie d'engin/).selectOption({ label: "Camion-benne rigide (tombereau)" });
  await qual.getByLabel("Valable à partir du").fill("2024-01-01");
  await qual.getByRole("button", { name: "Enregistrer l'habilitation" }).click();
  await expect(page.getByRole("row", { name: /Habilitation de conduite/ })).toContainText("sans échéance");
  // Le serveur dérive l'habilitation valide : le conducteur est habilité pour une catégorie.
  await page.goto("/conducteurs");
  await page.getByLabel("Recherche (nom, matricule)").fill(`M-UI-${suffix}`);
  await expect(page.getByRole("row", { name: new RegExp(`M-UI-${suffix}`) })).toContainText("1");
});

test("un rôle sans droit d'écriture ne voit pas les boutons de saisie", async ({ page }) => {
  const auditor = account("AUDITOR");
  await uiLogin(page, auditor);
  await page.goto("/vehicules");
  await expect(page.getByRole("heading", { name: "Véhicules et engins" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nouveau véhicule" })).toHaveCount(0);
  await page.getByRole("table").getByRole("link").first().click();
  await expect(page.getByRole("button", { name: "Changer le statut" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier" })).toHaveCount(0);
});
