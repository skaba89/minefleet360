import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : commande d'achat pièces — à partir d'une demande de réapprovisionnement
// approuvée (quatre-yeux fait par l'API ici, le parcours complet étant couvert par
// parts-replenishment.spec.ts), le chef d'atelier crée le brouillon de commande destiné au
// fournisseur depuis l'onglet « Commandes d'achat » de /pieces.
const WORKSPACE = "fictif-transport";

test("commande d'achat : brouillon créé depuis une demande approuvée, quantité reprise", async ({ page, request }) => {
  test.setTimeout(120_000);
  const chief = account("WORKSHOP_CHIEF", WORKSPACE);
  const chiefHeaders = await apiLogin(request, chief);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", WORKSPACE)));
  const opsHeaders = await apiLogin(request, account("OPS_MANAGER", WORKSPACE));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const part = await request.post("/api/v1/parts", {
    headers: chiefHeaders,
    data: { code: `P-PO-${suffix}`, name: `Filtre E2E commande ${suffix}`, unit: "EACH" },
  });
  expect(part.status(), await part.text()).toBe(201);
  const store = await request.post("/api/v1/part-stores", {
    headers: chiefHeaders,
    data: { site_id: site, code: `MAG-PO-${suffix}`, name: `Magasin commande ${suffix}` },
  });
  expect(store.status(), await store.text()).toBe(201);
  const reference = `REAP-PO-${suffix}`;
  const draft = await request.post("/api/v1/part-replenishments", {
    headers: chiefHeaders,
    data: {
      spare_part_store_id: (await store.json()).spare_part_store_id,
      spare_part_id: (await part.json()).spare_part_id,
      quantity: "6",
      reference,
    },
  });
  expect(draft.status(), await draft.text()).toBe(201);
  const replenishmentId = (await draft.json()).replenishment_id;
  const submitted = await request.post(`/api/v1/part-replenishments/${replenishmentId}/submit`, {
    headers: chiefHeaders,
  });
  expect(submitted.status(), await submitted.text()).toBe(200);
  const approved = await request.post(`/api/v1/part-replenishments/${replenishmentId}/decision`, {
    headers: opsHeaders,
    data: { action: "APPROVE", note: "Consommation prévue sur l'OT de la semaine (E2E commande)." },
  });
  expect(approved.status(), await approved.text()).toBe(200);

  // Le chef d'atelier crée la commande depuis l'UI : la quantité approuvée (6) est reprise.
  await uiLogin(page, chief);
  await page.goto("/pieces");
  await page.getByRole("button", { name: "Commandes d'achat" }).click();
  const orderForm = page.locator("form").filter({ hasText: "Créer une commande d'achat" });
  await orderForm.getByLabel("Demande approuvée").selectOption({ value: replenishmentId });
  await orderForm.getByLabel("Fournisseur", { exact: true }).fill("Fournisseur Hydraulique SARL");
  await orderForm.getByLabel("Référence fournisseur").fill(`FOU-${suffix}`);
  await orderForm.getByRole("button", { name: "Créer la commande" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Commande enregistrée comme brouillon" }).first()).toBeVisible();

  const orderRow = page.getByRole("row", { name: new RegExp(`FOU-${suffix}`) });
  await expect(orderRow).toContainText("Fournisseur Hydraulique SARL");
  await expect(orderRow).toContainText("6");
  await expect(orderRow).toContainText("Brouillon");
  await expect(orderRow).toContainText(reference);
});
