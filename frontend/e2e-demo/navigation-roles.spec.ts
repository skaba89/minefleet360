import { expect, test } from "@playwright/test";

import { demo, login } from "./demo";

// Recette de navigation par rôle sur le jeu QA éphémère. Les liens proviennent de
// l'interface réellement générée à partir des droits accordés par le backend.
const tenantRoles = [
  "TENANT_ADMIN", "DIRECTION", "OPS_MANAGER", "HR", "WORKSHOP_CHIEF",
  "STOREKEEPER", "HSE", "FINANCE", "AUDITOR",
] as const;
const siteRoles = ["DISPATCHER", "DRIVER", "MECHANIC", "FUEL_MANAGER"] as const;

for (const role of tenantRoles) {
  test(`navigation DEMO : tous les liens du rôle ${role} pointent vers une vraie page`, async ({ page }) => {
    test.setTimeout(120_000);
    await login(page, demo(role));
    const nav = page.getByRole("navigation", { name: "Navigation principale" });
    const hrefs = await nav.getByRole("link").evaluateAll((anchors) =>
      anchors.map((node) => (node as HTMLAnchorElement).getAttribute("href"))
        .filter((url): url is string => Boolean(url)),
    );
    expect(hrefs.length).toBeGreaterThan(1);

    for (const href of hrefs) {
      await page.goto(href);
      await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeVisible();
      await expect(page.getByText("Page introuvable.", { exact: true })).toHaveCount(0);
      await expect(page.getByText("Erreur inattendue.", { exact: true })).toHaveCount(0);
    }
  });
}

for (const role of siteRoles) {
  test(`navigation DEMO : compte site ${role} conserve un menu utilisable`, async ({ page }) => {
    await login(page, demo(role, "demo-bauxite", "BOKE-MINE"));
    const nav = page.getByRole("navigation", { name: "Navigation principale" });
    const links = nav.getByRole("link");
    expect(await links.count()).toBeGreaterThan(1);
    const href = await links.last().getAttribute("href");
    expect(href).toBeTruthy();
    await links.last().click();
    await expect(page.getByText("Page introuvable.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Erreur inattendue.", { exact: true })).toHaveCount(0);
  });
}

// Un chauffeur ne doit jamais recevoir les droits d'administration par
// commodité d'affichage : les vérifications servent aussi de garde anti-régression.
test("le conducteur n'accède pas aux menus administration et données inter-sociétés", async ({ page }) => {
  await login(page, demo("DRIVER", "demo-bauxite", "BOKE-MINE"));
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Administration", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Sociétés clientes", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Nouvelle société", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Coût complet", exact: true })).toHaveCount(0);
});
