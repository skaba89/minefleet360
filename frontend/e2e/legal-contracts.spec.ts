import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart recette UI : cycle juridique jouable hors harnais S3/ClamAV — brouillon créé depuis l'UI,
// soumission impossible sans document vérifié (règle « le digest seul n'est pas une preuve »).

test("contrat : brouillon créé depuis l'UI, soumission refusée sans preuve documentaire vérifiée", async ({ page, request }) => {
  test.setTimeout(90_000);
  const admin = account("TENANT_ADMIN");
  const adminHeaders = await apiLogin(request, admin);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", admin.workspace)));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const reference = `CTR-E2E-${suffix}`;

  // Sélection du site dans la barre supérieure : le formulaire de brouillon exige un site explicite.
  const sites = await (await request.get("/api/v1/sites", { headers: adminHeaders })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour l'admin").toBeTruthy();

  // 1. Création du brouillon depuis /juridique (sélection du site dans la barre supérieure :
  // le formulaire de brouillon exige un site explicite, chose faite dans la même session SPA).
  await uiLogin(page, admin);
  await page.goto("/juridique");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await page.getByLabel("Référence").fill(reference);
  await page.getByLabel("Intitulé").fill(`Contrat de fourniture de gasoil E2E ${suffix}`);
  await page.getByLabel("Contrepartie").fill(`Fournisseur E2E ${suffix}`);
  await page.getByLabel("Type de contrat").selectOption("SUPPLIER");
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  await expect(page.getByText("Contrat enregistré comme brouillon. Aucune signature n'a été effectuée.")).toBeVisible();
  const draftRow = page.getByRole("row", { name: new RegExp(reference) });
  await expect(draftRow).toContainText("DRAFT");

  // 2. La soumission est refusée par le serveur tant qu'aucun document vérifié ne prouve le contrat
  //    (upload S3 + analyse ClamAV hors de l'environnement E2E ; le digest seul n'est pas une preuve).
  const contracts = await (
    await request.get("/api/v1/legal-contracts", { headers: adminHeaders, params: { page_size: 200 } })
  ).json();
  const contract = contracts.items.find((c: { reference: string }) => c.reference === reference);
  expect(contract, "contrat introuvable via l'API").toBeTruthy();
  const submit = await request.post(`/api/v1/legal-contracts/${contract.contract_id}/submit`, { headers: adminHeaders });
  expect(submit.status()).toBe(409);
  const body = await submit.json();
  expect(body.code).toBe("CONFLICT");

  // 3. L'UI ne propose pas de soumission directe d'un brouillon sans pièce justificative.
  await expect(page.getByRole("button", { name: /Soumettre/i })).toHaveCount(0);
  await expect(draftRow).toContainText("DRAFT");
});
