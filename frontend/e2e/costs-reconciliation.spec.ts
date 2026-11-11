import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Recette UI : actions de coûts (taux horaires de main-d'œuvre) depuis /couts et réconciliation
// du stockage documentaire depuis /juridique. La réconciliation est prouvée sur son chemin
// dégradé : sans stockage privé configuré (S3/MinIO), le serveur répond 503 SERVICE_BUSY et
// l'interface affiche une erreur en français sans casser la page — le chemin nominal requiert le
// harnais S3/ClamAV (écart n°1 de RECETTE_UI_P0.md §4). Les refus RBAC sont vérifiés en UI
// (forme canonique <AccessDenied />) et en API.

/** Date ISO (AAAA-MM-JJ) décalée de n jours — le navigateur E2E tourne en UTC (Africa/Conakry). */
function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

test("taux horaires : création FINANCE depuis /couts, contrôle croisé API, AUDITOR lecture seule, DISPATCHER refusé", async ({ browser, page, request }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const finance = account("FINANCE", dispatcher.workspace);
  const financeHeaders = await apiLogin(request, finance);
  const sites = await (await request.get("/api/v1/sites", { headers: financeHeaders })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour FINANCE").toBeTruthy();
  const validFrom = isoDate(0);

  // 1. La FINANCE crée un taux horaire de site depuis l'UI (devise GNF par défaut).
  await uiLogin(page, finance);
  await page.goto("/couts");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  const tauxRegion = page.getByRole("region", { name: "Taux horaires de main-d'œuvre" });
  await tauxRegion.getByRole("button", { name: "Ajouter un taux" }).click();
  const form = page.getByRole("form", { name: "Nouveau taux horaire" });
  await form.getByLabel("Portée").selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await form.getByLabel("Taux horaire").fill("12500");
  await form.getByLabel("Date d'effet").fill(validFrom);
  await form.getByRole("button", { name: "Enregistrer" }).click();

  // La liste affiche le taux au niveau du site, valorisé en GNF à sa date d'effet
  // (.first() : les re-exécutions locales créent un taux par jour d'exécution).
  const rateRow = tauxRegion.locator("li").filter({ hasText: siteInfo.code });
  await expect(rateRow.filter({ hasText: `depuis le ${validFrom}` }).first()).toBeVisible();
  await expect(rateRow.filter({ hasText: "GNF / h" }).first()).toBeVisible();

  // 2. Contrôle croisé API : le taux est persisté pour le bon site à la bonne date.
  const rates = await (await request.get("/api/v1/costs/labour-rates", { headers: financeHeaders })).json();
  const created = rates.find(
    (r: { site_id: string | null; valid_from: string }) => r.site_id === site && r.valid_from === validFrom,
  );
  expect(created, "taux horaire absent de la liste API").toBeTruthy();
  expect(Number(created.hourly_rate)).toBe(12500);
  expect(created.currency).toBe("GNF");

  // 3. L'AUDITOR lit les coûts complets mais ne dispose d'aucune section de gestion des taux.
  const auditorContext = await browser.newContext();
  const auditorPage = await auditorContext.newPage();
  await uiLogin(auditorPage, account("AUDITOR", dispatcher.workspace));
  await auditorPage.goto("/couts");
  await auditorPage.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await expect(auditorPage.getByRole("heading", { name: "Taux horaires de main-d'œuvre" })).toHaveCount(0);
  await expect(auditorPage.getByRole("button", { name: "Ajouter un taux" })).toHaveCount(0);
  await auditorContext.close();

  // 4. Le DISPATCHER n'a pas accès aux coûts : la page n'a pas de pré-contrôle, le 403 serveur
  //    s'affiche sous la forme canonique « …cette information » (défense en profondeur) ; 403 en API.
  const dispatcherContext = await browser.newContext();
  const dispatcherPage = await dispatcherContext.newPage();
  await uiLogin(dispatcherPage, dispatcher);
  await dispatcherPage.goto("/couts");
  await expect(dispatcherPage.getByText("Vous n'avez pas accès à cette information.")).toBeVisible();
  await dispatcherContext.close();
  const denied = await request.post("/api/v1/costs/labour-rates", {
    headers: await apiLogin(request, dispatcher),
    data: { site_id: site, hourly_rate: "1000", currency: "GNF", valid_from: validFrom },
  });
  expect(denied.status()).toBe(403);
});

test("réconciliation du stockage documentaire : panneau DIRECTION, dégradation 503 annoncée, AUDITOR sans panneau", async ({ browser, page, request }) => {
  test.setTimeout(120_000);
  const workspace = account("DISPATCHER").workspace;
  const direction = account("DIRECTION", workspace);
  const directionHeaders = await apiLogin(request, direction);

  // 1. La DIRECTION dispose du panneau « Intégrité des documents » sur /juridique (revue tenant).
  await uiLogin(page, direction);
  await page.goto("/juridique");
  const panneau = page.getByRole("region", { name: "Contrôle du stockage documentaire" });
  await expect(panneau.getByRole("heading", { name: "Intégrité des documents" })).toBeVisible();

  // 2. Sans stockage privé configuré sur ce serveur, le contrôle répond 503 SERVICE_BUSY :
  //    l'interface affiche l'erreur en français et la page reste utilisable (pas de crash).
  await panneau.getByRole("button", { name: "Contrôler le stockage" }).click();
  await expect(panneau.getByText("Service momentanément occupé. Réessayez dans quelques instants.")).toBeVisible();
  const direct = await request.get("/api/v1/legal-contracts/storage-reconciliation", { headers: directionHeaders });
  expect(direct.status()).toBe(503);

  // 3. L'AUDITOR, lecteur des registres, ne dispose ni du panneau ni de l'endpoint (403).
  const auditorContext = await browser.newContext();
  const auditorPage = await auditorContext.newPage();
  await uiLogin(auditorPage, account("AUDITOR", workspace));
  await auditorPage.goto("/juridique");
  await expect(auditorPage.getByRole("button", { name: "Contrôler le stockage" })).toHaveCount(0);
  await auditorContext.close();
  const auditorHeaders = await apiLogin(request, account("AUDITOR", workspace));
  const denied = await request.get("/api/v1/legal-contracts/storage-reconciliation", { headers: auditorHeaders });
  expect(denied.status()).toBe(403);
});
