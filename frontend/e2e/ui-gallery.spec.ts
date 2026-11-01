/**Capture d'écrans réels à partir de comptes EXCLUSIVEMENT fictifs.

Exécution manuelle : npm run e2e -- ui-gallery.spec.ts
Les images sont conservées uniquement dans un dossier local ignoré par Git.
 */
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { account, uiLogin } from "./fixtures";

const destination = resolve("artifacts", "ui-gallery");
const pages = [
  { slug: "accueil", route: "/" },
  { slug: "vehicules", route: "/vehicules" },
  { slug: "conducteurs", route: "/conducteurs" },
  { slug: "affectations", route: "/affectations" },
  { slug: "missions", route: "/missions" },
  { slug: "gps", route: "/flotte-gps" },
  { slug: "atelier", route: "/atelier" },
  { slug: "maintenance", route: "/maintenance" },
  { slug: "carburant", route: "/carburant" },
  { slug: "pieces", route: "/pieces" },
  { slug: "juridique", route: "/juridique" },
  { slug: "pesees", route: "/pesees" },
  { slug: "indicateurs", route: "/indicateurs" },
] as const;

test("galerie des écrans métier sur données fictives", async ({ page }) => {
  test.skip(process.env.MF_UI_GALLERY !== "1", "Capture manuelle uniquement (MF_UI_GALLERY=1).");
  const demo = account("TENANT_ADMIN", "fictif-transport");
  if (!demo.workspace.startsWith("fictif-")) {
    throw new Error("Capture refusée : seul un espace de travail fictif est autorisé.");
  }
  await uiLogin(page, demo);
  await mkdir(destination, { recursive: true });
  for (const item of pages) {
    await page.goto(item.route);
    await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeVisible();
    await expect(page).not.toHaveURL(/\/connexion(?:\?|$)/);
    await page.screenshot({ path: resolve(destination, `${item.slug}.png`), fullPage: true, animations: "disabled" });
  }
});
