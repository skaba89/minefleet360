import { expect, test } from "@playwright/test";

import { account, uiLogin } from "./fixtures";

// Administration d'une société fictive par son TENANT_ADMIN : sites, utilisateurs et rôles, journal.

test("l'administrateur crée un site, invite un utilisateur, gère ses rôles et retrouve l'audit", async ({ page }) => {
  const admin = account("TENANT_ADMIN");
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  await uiLogin(page, admin);
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: "Administration" }).click();

  // Site
  await page.getByRole("button", { name: "Nouveau site" }).click();
  const siteForm = page.getByRole("form", { name: "Nouveau site" });
  await siteForm.getByLabel("Code (unique, définitif)").fill(`UI${suffix}`);
  await siteForm.getByLabel("Nom").fill(`Site UI ${suffix}`);
  await siteForm.getByLabel("Type").selectOption({ label: "Dépôt" });
  await siteForm.getByLabel("Fuseau horaire").selectOption("Africa/Lagos");
  await siteForm.getByRole("button", { name: "Créer le site" }).click();
  await expect(page.getByRole("row", { name: new RegExp(`UI${suffix}`) })).toContainText("Africa/Lagos");

  // Invitation avec rôle de portée site
  await page.getByRole("navigation", { name: "Administration" }).getByRole("link", { name: "Utilisateurs et rôles" }).click();
  await page.getByRole("button", { name: "Inviter un utilisateur" }).click();
  const invite = page.getByRole("form", { name: "Inviter un utilisateur" });
  const email = `invite.${suffix.toLowerCase()}@example.com`;
  await invite.getByLabel("Adresse e-mail").fill(email);
  await invite.getByLabel("Nom affiché").fill(`Invité ${suffix}`);
  await invite.getByLabel("Rôle").selectOption("DISPATCHER");
  await invite.getByLabel(/^Site/).selectOption({ label: `UI${suffix} — Site UI ${suffix}` });
  await invite.getByRole("button", { name: "Envoyer l'invitation" }).click();
  await page.getByLabel("Statut").selectOption({ label: "Invité" });
  await page.getByRole("button", { name: `Invité ${suffix}` }).click();
  const panel = page.locator(".card", { has: page.getByRole("heading", { name: `Invité ${suffix}` }) });
  await expect(panel.getByRole("row", { name: /Dispatcher/ })).toContainText(`UI${suffix}`);

  // Ajout puis retrait d'un rôle
  await panel.getByRole("button", { name: "Ajouter un rôle" }).click();
  const add = page.getByRole("form", { name: "Ajouter un rôle" });
  await add.getByLabel("Rôle").selectOption("HSE");
  await add.getByRole("button", { name: "Attribuer le rôle" }).click();
  await expect(panel.getByRole("row", { name: /HSE/ })).toContainText("Toute la société");
  await panel.getByRole("row", { name: /HSE/ }).getByRole("button", { name: "Retirer" }).click();
  await expect(panel.getByRole("status")).toContainText("Rôle retiré.");
  await expect(panel.getByRole("row", { name: /HSE/ })).toHaveCount(0);

  // Journal d'audit
  await page.getByRole("navigation", { name: "Administration" }).getByRole("link", { name: "Journal d'audit" }).click();
  await page.getByLabel("Type d'élément").selectOption({ label: "Rôle" });
  await expect(page.getByRole("cell", { name: "role_assignment.revoke" }).first()).toBeVisible();
});

test("sans droit d'administration, l'URL directe ne propose aucune action", async ({ page }) => {
  await uiLogin(page, account("DISPATCHER"));
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
  await page.goto("/administration/sites");
  await expect(page.getByRole("alert")).toContainText("Vous n'avez pas accès");
  await expect(page.getByRole("button", { name: "Nouveau site" })).toHaveCount(0);
});

test("l'auditeur lit le journal sans pouvoir administrer les sites", async ({ page }) => {
  await uiLogin(page, account("AUDITOR"));
  await page.goto("/administration");
  await expect(page.getByRole("navigation", { name: "Administration" }).getByRole("link")).toHaveText([
    "Utilisateurs et rôles",
    "Journal d'audit",
  ]);
  await page.goto("/administration/sites");
  await expect(page.getByRole("alert")).toContainText("Vous n'avez pas accès");
});
