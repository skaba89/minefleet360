import { expect, test, type APIRequestContext } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : action corrective HSE — création sur incident, réalisation par le responsable, vérification.

async function post(request: APIRequestContext, url: string, headers: Record<string, string>, data: unknown) {
  const resp = await request.post(url, { headers, data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  return resp.json();
}

test("action corrective HSE : ajout sur incident, réalisation par le responsable, vérification HSE", async ({ browser, request }) => {
  test.setTimeout(120_000);
  const hse = account("HSE");
  const chief = account("WORKSHOP_CHIEF", hse.workspace);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", hse.workspace)));
  const hseHeaders = await apiLogin(request, hse);
  const chiefHeaders = await apiLogin(request, chief);
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();

  // Incident déclaré par l'API (la déclaration hors ligne est couverte par e2e-field/hse-offline.spec.ts).
  const incident = await post(request, "/api/v1/hse/incidents", hseHeaders, {
    site_id: site,
    category: "NEAR_MISS",
    severity: "LOW",
    title: `Presque-accident éclairage fosse E2E ${suffix}`,
    description: "Un éclairage défaillant de la fosse a failli provoquer une collision entre deux engins durant le poste de nuit.",
    occurred_at: new Date().toISOString(),
    location_note: "Fosse principale",
  });

  // Le chef d'atelier est éligible comme responsable : retrouvé dans la liste des responsables proposés.
  const chiefProfile = await (await request.get("/api/v1/me", { headers: chiefHeaders })).json();
  const owners = await (
    await request.get(`/api/v1/hse/incidents/${incident.hse_incident_id}/action-owners`, { headers: hseHeaders })
  ).json();
  const chiefOwner = owners.find((o: { display_name: string }) => o.display_name === chiefProfile.display_name);
  expect(chiefOwner, "chef d'atelier absent des responsables éligibles").toBeTruthy();

  // 1. Le HSE ajoute l'action corrective depuis la fiche incident.
  const hseContext = await browser.newContext();
  const hsePage = await hseContext.newPage();
  await uiLogin(hsePage, hse);
  const title = `Remplacer l'éclairage de la fosse E2E ${suffix}`;
  await hsePage.goto(`/hse/${incident.hse_incident_id}`);
  await hsePage.getByRole("button", { name: "Ajouter une action corrective" }).click();
  const actionForm = hsePage.getByRole("form", { name: "Ajouter une action corrective" });
  await actionForm.getByLabel("Action").fill(title);
  await actionForm.getByLabel("Responsable").selectOption({ value: chiefOwner.user_account_id });
  await actionForm.getByLabel("Échéance").fill(new Date(Date.now() + 86_400_000).toISOString().slice(0, 10));
  await actionForm.getByRole("button", { name: "Ajouter", exact: true }).click();
  const actionRow = hsePage.getByRole("row", { name: new RegExp(title) });
  await expect(actionRow).toContainText("À réaliser");

  // 2. Le responsable déclare la réalisation depuis son espace HSE.
  const chiefContext = await browser.newContext();
  const chiefPage = await chiefContext.newPage();
  await uiLogin(chiefPage, chief);
  await chiefPage.goto("/hse");
  await expect(chiefPage.getByRole("heading", { name: "Mes actions correctives à réaliser" })).toBeVisible();
  await expect(chiefPage.getByText(title)).toBeVisible();
  await chiefPage.getByRole("link", { name: new RegExp(incident.reference) }).first().click();
  const chiefRow = chiefPage.getByRole("row", { name: new RegExp(title) });
  await chiefRow.getByRole("button", { name: "Déclarer réalisée" }).click();
  const completeForm = chiefPage.getByRole("form", { name: `Déclarer réalisée : ${title}` });
  await completeForm.getByLabel("Ce qui a été fait").fill("Deux luminaires remplacés et testés en présence du chef de poste.");
  await completeForm.getByRole("button", { name: "Déclarer réalisée" }).click();
  await expect(chiefRow).toContainText("Réalisée, à vérifier");
  await chiefContext.close();

  // 3. Le HSE vérifie l'action réalisée (double regard : vérificateur ≠ réalisateur).
  await hsePage.goto(`/hse/${incident.hse_incident_id}`);
  const verifyRow = hsePage.getByRole("row", { name: new RegExp(title) });
  await verifyRow.getByRole("button", { name: "Vérifier" }).click();
  await expect(verifyRow).toContainText("Vérifiée");
  await hseContext.close();
  await chiefContext.close();
});
