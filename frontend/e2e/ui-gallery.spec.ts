/**Capture d'écrans réels à partir de comptes EXCLUSIVEMENT fictifs.

Exécution manuelle : npm run e2e -- ui-gallery.spec.ts
Les images sont conservées uniquement dans un dossier local ignoré par Git.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

import { account, uiLogin } from "./fixtures";

const destination = resolve("artifacts", "ui-gallery");
const pages = [
  { slug: "accueil", route: "/", label: "Tableau de bord", maturity: "avancé" },
  { slug: "vehicules", route: "/vehicules", label: "Véhicules", maturity: "avancé" },
  { slug: "conducteurs", route: "/conducteurs", label: "Conducteurs", maturity: "avancé" },
  { slug: "affectations", route: "/affectations", label: "Affectations", maturity: "avancé" },
  { slug: "missions", route: "/missions", label: "Missions", maturity: "avancé" },
  { slug: "gps", route: "/flotte-gps", label: "GPS", maturity: "partiel" },
  { slug: "atelier", route: "/atelier", label: "Atelier", maturity: "partiel" },
  { slug: "maintenance", route: "/maintenance", label: "Maintenance", maturity: "partiel" },
  { slug: "carburant", route: "/carburant", label: "Carburant", maturity: "avancé" },
  { slug: "pieces", route: "/pieces", label: "Pièces", maturity: "partiel" },
  { slug: "juridique", route: "/juridique", label: "Juridique", maturity: "partiel" },
  { slug: "pesees", route: "/pesees", label: "Pesées", maturity: "avancé" },
  { slug: "indicateurs", route: "/indicateurs", label: "Indicateurs", maturity: "partiel" },
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
  const cards = pages.map((item) => `<article><h2>${item.label}</h2><p>${item.maturity} · ${item.route}</p><a href="${item.slug}.png"><img loading="lazy" alt="${item.label}" src="${item.slug}.png"></a></article>`).join("\n");
  const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MineFleet360 — Galerie locale</title><style>body{font:16px system-ui;background:#f4f6f9;color:#172337;max-width:1400px;margin:auto;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}article{background:white;border:1px solid #dae0e8;border-radius:12px;padding:16px}h2{margin:0}p{color:#526277}img{width:100%;height:auto;border-radius:6px}</style></head><body><h1>MineFleet360 — Interfaces réelles</h1><p>Captures locales sur des données fictives ; les niveaux de maturité sont indicatifs, pas des validations fonctionnelles.</p><main>${cards}</main></body></html>`;
  await writeFile(resolve(destination, "index.html"), html, "utf8");
});
