import { expect, test } from "@playwright/test";

import { demo, login, platformAccount, loginPlatform } from "./demo";

// Recette P0 (docs/qa/RECETTE_UI_P0.md) : chaque page protégée doit rester saine pour chaque rôle,
// y compris en accès direct par URL — les menus filtrent, l'URL ne doit rien révéler et ne doit
// jamais faire planter l'interface. Attendu par page : soit un contenu autorisé, soit un refus
// explicite (403 en français ou message dédié de la page), jamais « Page introuvable. » ni
// « Erreur inattendue. » ni un écran vide sans shell de navigation.
const routes = [
  "/",
  "/plateforme/societes",
  "/plateforme/nouvelle-societe",
  "/plateforme/etat",
  "/vehicules",
  "/vehicules/echeances",
  "/flotte-gps",
  "/flotte-gps/zones",
  "/flotte-gps/alertes",
  "/mon-suivi",
  "/conducteurs",
  "/affectations",
  "/missions",
  "/atelier",
  "/atelier/fiabilite",
  "/maintenance",
  "/carburant",
  "/pieces",
  "/pneus",
  "/hse",
  "/hse/inspections",
  "/hse/checklists",
  "/pesees",
  "/indicateurs",
  "/juridique",
  "/couts",
  "/mon-compte/securite",
  "/mon-compte/sessions",
  "/administration",
  "/administration/sites",
  "/administration/utilisateurs",
  "/administration/journal",
  "/administration/lieux-matieres",
  "/administration/documents-exiges",
] as const;

const roles: Array<[string, string | null]> = [
  ["TENANT_ADMIN", null],
  ["DIRECTION", null],
  ["OPS_MANAGER", null],
  ["HR", null],
  ["WORKSHOP_CHIEF", null],
  ["STOREKEEPER", null],
  ["HSE", null],
  ["FINANCE", null],
  ["AUDITOR", null],
  ["DISPATCHER", "BOKE-MINE"],
  ["DRIVER", "BOKE-MINE"],
  ["MECHANIC", "BOKE-MINE"],
  ["FUEL_MANAGER", "BOKE-MINE"],
];

for (const [role, site] of roles) {
  test(`accès direct par URL : toutes les pages protégées restent saines pour ${role}`, async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await login(page, demo(role, "demo-bauxite", site));
    for (const route of routes) {
      await page.goto(route);
      await expect(
        page.getByRole("navigation", { name: "Navigation principale" }),
      ).toBeVisible();
      await expect(
        page.getByText("Page introuvable.", { exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByText("Erreur inattendue.", { exact: true }),
      ).toHaveCount(0);
    }
  });
}

// L'administrateur plateforme ne porte jamais de droit métier privé : les pages plateforme
// chargent, l'interface métier reste hors de son menu et toute URL métier répond un refus propre.
test("accès direct PLATFORM_ADMIN : pages plateforme saines, aucun droit métier privé", async ({
  page,
}) => {
  const account = platformAccount();
  if (!account) {
    test.skip(
      true,
      "MF_PLATFORM_ACCOUNT absent du run : compte plateforme non fourni",
    );
    return;
  }
  await loginPlatform(page, account);
  for (const route of [
    "/",
    "/plateforme/societes",
    "/plateforme/nouvelle-societe",
    "/plateforme/etat",
  ]) {
    await page.goto(route);
    await expect(
      page.getByRole("navigation", { name: "Navigation principale" }),
    ).toBeVisible();
    await expect(
      page.getByText("Page introuvable.", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("Erreur inattendue.", { exact: true }),
    ).toHaveCount(0);
  }
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(
    nav.getByRole("link", { name: "Véhicules", exact: true }),
  ).toHaveCount(0);
  await expect(
    nav.getByRole("link", { name: "Missions", exact: true }),
  ).toHaveCount(0);
  await expect(
    nav.getByRole("link", { name: "Coût complet", exact: true }),
  ).toHaveCount(0);
  await page.goto("/vehicules");
  await expect(
    page
      .getByText("Vous n'avez pas accès à cette information.")
      .or(page.getByText("Aucun élément à afficher.")),
  ).toBeVisible();
});
