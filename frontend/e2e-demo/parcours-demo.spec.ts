import { expect, test } from "@playwright/test";

import { demo, login, open } from "./demo";

// Parcours par rôle sur le jeu DEMO (profil qa) : chaque écran affiche des données réellement chargées,
// jamais des chiffres codés dans l'interface ; les refus de droits et l'isolation sont visibles.

test("direction : tableau de bord et point critique à traiter", async ({ page }) => {
  await login(page, demo("AUDITOR"));
  await expect(page.getByText("DEMO — Bauxite Guinée Operations")).toBeVisible();
  await expect(page.getByText(/incident\(s\) critique\(s\) non clôturé\(s\)/)).toBeVisible();
  await expect(page.getByText("Véhicules disponibles")).toBeVisible();
});

test("dispatcher : missions en cours du jour et détail d'une mission terminée", async ({ page }) => {
  await login(page, demo("DISPATCHER", "demo-bauxite", "BOKE-MINE"));
  await open(page, "Missions");
  const rows = page.getByRole("row").filter({ hasText: /DEMO-CAM-\d{3}/ });
  await expect(rows.first()).toBeVisible();
  await expect(rows.filter({ hasText: /En chargement|En route chargé|En déchargement/ }).first()).toBeVisible();
  await page.getByLabel("En cours seulement").uncheck();
  await page.getByLabel("Statut").selectOption({ label: "Terminée" });
  await page.getByRole("row").filter({ hasText: "Terminée" }).first().getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: "Rotations" })).toBeVisible();
  // Chaque rotation terminée porte une pesée pont-bascule valide (tonnage réellement mesuré).
  await expect(page.getByRole("row").filter({ hasText: /Terminée.*\d+,\d{2} t \(Valide\)/ }).first()).toBeVisible();
});

test("auditeur : tonnage mesuré et coût complet valorisé en GNF", async ({ page }) => {
  await login(page, demo("AUDITOR"));
  await open(page, "Indicateurs");
  await expect(page.getByRole("row").filter({ hasText: "Bauxite" }).first()).toBeVisible();
  await expect(page.getByText(/\d[\d\s ]*,\d{2} t/).first()).toBeVisible();
  await open(page, "Coût complet");
  await expect(page.getByRole("row").filter({ hasText: "DEMO-CAM-" }).first()).toBeVisible();
  await expect(page.getByText("Estimé").first()).toBeVisible();
  await expect(page.getByText(/\d[\d\s ]* GNF/).first()).toBeVisible();
});

test("auditeur : trajet GPS d'un camion avec franchissement de zones (consultation journalisée)", async ({ page }) => {
  await login(page, demo("AUDITOR"));
  await open(page, "Flotte GPS");
  await expect(page.getByText("Camions localisés")).toBeVisible();
  await open(page, "Véhicules");
  await page.getByRole("link", { name: "DEMO-CAM-001" }).first().click();
  await page.getByLabel("Finalité").selectOption({ label: "Analyse d'exploitation" });
  const now = new Date();
  const start = new Date(now.getTime() - 2 * 86_400_000);
  const day = (d: Date) => d.toISOString().slice(0, 10);
  const range = page.locator('input[type="datetime-local"]');
  await range.nth(0).fill(`${day(start)}T00:00`);
  await range.nth(1).fill(`${day(new Date(start.getTime() + 86_400_000))}T00:00`);
  await page.getByRole("button", { name: "Afficher le trajet" }).click();
  await expect(page.getByText(/Distance mesurée/)).toBeVisible();
  await expect(page.getByText(/Entrée : Aire de chargement \(DEMO\)/).first()).toBeVisible();
});

test("chef d'atelier : panne ouverte sur engin immobilisé", async ({ page }) => {
  await login(page, demo("WORKSHOP_CHIEF"));
  await open(page, "Atelier");
  await expect(page.getByRole("row").filter({ hasText: "DEMO-CAM-" }).filter({ hasText: "Demandé" }).first()).toBeVisible();
});

test("HSE : incident critique ouvert et inspection non conforme", async ({ page }) => {
  await login(page, demo("HSE"));
  await open(page, "Sécurité (HSE)");
  await expect(page.getByText("Collision d'engin contre un merlon de sécurité")).toBeVisible();
  await page.getByRole("link", { name: "Inspections et checklists" }).click();
  await page.getByLabel("Résultat").selectOption({ label: "Non conforme (critique)" });
  await expect(page.getByText(/INS-\d{6}/).first()).toBeVisible();
});

test("conducteur : aucun accès au parc", async ({ page }) => {
  await login(page, demo("DRIVER", "demo-bauxite", "BOKE-MINE"));
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Véhicules", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Coût complet", exact: true })).toHaveCount(0);
});

test("isolation : un compte d'une société est refusé dans l'espace d'une autre", async ({ page }) => {
  const ops = demo("OPS_MANAGER");
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill("demo-tlm");
  await page.getByLabel("Adresse e-mail").fill(ops.email);
  await page.getByLabel("Mot de passe").fill(ops.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Navigation principale" })).toHaveCount(0);
});
