import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : réapprovisionnement pièces — création, soumission, quatre-yeux à la décision.

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

function replenishmentRow(page: Page, reference: string) {
  return page.getByRole("row", { name: new RegExp(reference) });
}

test("réapprovisionnement : brouillon, soumission, auto-décision refusée, approbation par un autre", async ({ browser, request }) => {
  test.setTimeout(120_000);
  const chief = account("WORKSHOP_CHIEF");
  const chiefHeaders = await apiLogin(request, chief);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", chief.workspace)));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const part = await post(request, "/api/v1/parts", chiefHeaders, {
    code: `P-E2E-${suffix}`,
    name: `Filtre hydraulique E2E ${suffix}`,
  });
  const store = await post(request, "/api/v1/part-stores", chiefHeaders, {
    site_id: site,
    code: `MAG-E2E-${suffix}`,
    name: `Magasin E2E ${suffix}`,
  });
  const reference = `REAP-E2E-${suffix}`;

  // 1. Le chef d'atelier crée puis soumet la demande depuis /pieces.
  const chiefContext = await browser.newContext();
  const chiefPage = await chiefContext.newPage();
  await uiLogin(chiefPage, chief);
  await chiefPage.goto("/pieces");
  await chiefPage.getByRole("button", { name: "Réapprovisionnements" }).click();
  const draftForm = chiefPage.locator("form").filter({ hasText: "Créer une demande de réapprovisionnement" });
  await draftForm.getByLabel("Pièce").selectOption({ label: `${part.code} — ${part.name}` });
  await draftForm.getByLabel("Magasin").selectOption({ label: `${store.code} — ${store.name}` });
  await draftForm.getByLabel("Quantité").fill("6");
  await draftForm.getByLabel("Référence unique").fill(reference);
  await draftForm.getByRole("button", { name: "Créer le brouillon" }).click();
  const row = replenishmentRow(chiefPage, reference);
  await expect(row).toContainText("Brouillon");
  await row.getByRole("button", { name: "Soumettre" }).click();
  await expect(row).toContainText("Soumis");

  // 2. Quatre-yeux : le créateur ne peut pas décider sa propre demande (409 affiché en français).
  await chiefPage.getByLabel("Justification de la décision (obligatoire)").fill("Stock confirmé sur le magasin E2E.");
  await row.getByRole("button", { name: "Approuver" }).click();
  await expect(chiefPage.getByText("Conflit avec l'état actuel des données.").first()).toBeVisible();
  await expect(row).toContainText("Soumis");
  await chiefContext.close();

  // 3. L'OPS_MANAGER (autre personne) approuve avec la justification tracée.
  const opsContext = await browser.newContext();
  const opsPage = await opsContext.newPage();
  await uiLogin(opsPage, account("OPS_MANAGER", chief.workspace));
  await opsPage.goto("/pieces");
  await opsPage.getByRole("button", { name: "Réapprovisionnements" }).click();
  const opsRow = replenishmentRow(opsPage, reference);
  await expect(opsRow).toContainText("Soumis");
  await opsPage.getByLabel("Justification de la décision (obligatoire)").fill("Consommation prévue sur l'OT de la semaine.");
  await opsRow.getByRole("button", { name: "Approuver" }).click();
  await expect(opsRow).toContainText("Approuvé");
  await opsContext.close();
});
