import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : police d'assurance créée depuis /juridique (FINANCE), échéances traduites
// (EXPIRING / EXPIRED), borne d'horizon, auditeur en lecture seule. Le cycle documentaire des
// contrats reste hors de portée (harnais S3/ClamAV) : voir e2e/legal-contracts.spec.ts.

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

/** Date ISO (AAAA-MM-JJ) décalée de n jours — le navigateur E2E tourne en UTC (Africa/Conakry). */
function isoDate(offsetDays: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

function echeancesRegion(page: Page) {
  return page.getByRole("region", { name: "Échéances d'assurance" });
}

test("police d'assurance : création FINANCE depuis /juridique, échéances traduites, auditeur lecture seule", async ({ browser, page, request }) => {
  test.setTimeout(120_000);
  const finance = account("FINANCE");
  const financeHeaders = await apiLogin(request, finance);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", finance.workspace)));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const sites = await (await request.get("/api/v1/sites", { headers: financeHeaders })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour FINANCE").toBeTruthy();

  // Préparation par l'API : une police déjà expirée et une hors horizon (fin à +90 jours),
  // pour prouver la traduction des états et la borne du panneau d'échéances (45 jours).
  await post(request, "/api/v1/insurance-policies", financeHeaders, {
    site_id: site,
    policy_number: `POL-EXP-E2E-${suffix}`,
    insurer_name: `Assureur E2E ${suffix}`,
    coverage_type: "FLEET",
    coverage_start: isoDate(-40),
    coverage_end: isoDate(-10),
    currency: "GNF",
  });
  const horizonNumber = `POL-HOR-E2E-${suffix}`;
  await post(request, "/api/v1/insurance-policies", financeHeaders, {
    site_id: site,
    policy_number: horizonNumber,
    insurer_name: `Assureur E2E ${suffix}`,
    coverage_type: "VEHICLE",
    coverage_start: isoDate(0),
    coverage_end: isoDate(90),
    currency: "GNF",
  });

  // 1. FINANCE crée la police depuis l'onglet Assurances (site choisi dans la barre supérieure).
  const policyNumber = `POL-E2E-${suffix}`;
  await uiLogin(page, finance);
  await page.goto("/juridique");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await page.getByRole("button", { name: "Assurances" }).click();
  await page.getByLabel("Numéro de police").fill(policyNumber);
  await page.getByLabel("Assureur").fill(`Assureur E2E ${suffix}`);
  await page.getByLabel("Type de couverture").selectOption("CARGO");
  await page.getByLabel("Début de couverture").fill(isoDate(-10));
  await page.getByLabel("Fin de couverture").fill(isoDate(30));
  await page.getByRole("button", { name: "Enregistrer la police" }).click();
  await expect(page.getByText("Police enregistrée. Vérifiez les documents auprès de votre assureur.")).toBeVisible();

  // 2. La police apparaît dans « Polices enregistrées » (avec l'échéance : 2 lignes au total).
  await expect(page.getByRole("row", { name: new RegExp(policyNumber) })).toHaveCount(2);
  const echeances = echeancesRegion(page);
  await expect(echeances.getByRole("row", { name: new RegExp(policyNumber) })).toContainText("Échéance proche");

  // 3. Le panneau traduit les états : « Expirée » pour la police passée, rien au-delà de l'horizon.
  await expect(echeances.getByRole("row", { name: new RegExp(`POL-EXP-E2E-${suffix}`) })).toContainText("Expirée");
  await expect(echeances.getByRole("row", { name: new RegExp(horizonNumber) })).toHaveCount(0);
  await expect(page.getByRole("row", { name: new RegExp(horizonNumber) })).toHaveCount(1);

  // 4. Contrôle croisé API : l'endpoint d'échéances classe la nouvelle police en EXPIRING.
  const expiring = await (
    await request.get("/api/v1/insurance-policies/expiring", {
      headers: financeHeaders,
      params: { site_id: site, within_days: 45 },
    })
  ).json();
  const found = expiring.find((p: { policy_number: string }) => p.policy_number === policyNumber);
  expect(found, "police absente des échéances (API)").toBeTruthy();
  expect(found.validity).toBe("EXPIRING");

  // 5. L'AUDITOR lit les registres mais ne dispose d'aucun formulaire de création.
  const auditorContext = await browser.newContext();
  const auditorPage = await auditorContext.newPage();
  await uiLogin(auditorPage, account("AUDITOR", finance.workspace));
  await auditorPage.goto("/juridique");
  await auditorPage.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await auditorPage.getByRole("button", { name: "Assurances" }).click();
  await expect(echeancesRegion(auditorPage)).toBeVisible();
  await expect(auditorPage.getByRole("heading", { name: "Nouvelle police d'assurance" })).toHaveCount(0);
  await expect(auditorPage.getByRole("button", { name: "Enregistrer la police" })).toHaveCount(0);
  await expect(auditorPage.getByRole("row", { name: new RegExp(policyNumber) }).first()).toBeVisible();
  await auditorContext.close();
});
