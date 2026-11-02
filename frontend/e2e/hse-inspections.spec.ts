import { expect, test } from "@playwright/test";

import { account, apiLogin, uiLogin } from "./fixtures";

/** Inspection de prise de poste non conforme, action corrective, preuves refusées sans antivirus configuré. */
test("inspection non conforme puis action corrective", async ({ page, browser, request }) => {
  const hse = account("HSE");
  const hseHeaders = await apiLogin(request, hse);
  const code = `E2E-PRE-${Date.now()}`;
  const template = await request.post("/api/v1/hse/checklist-templates", {
    headers: hseHeaders,
    data: {
      code,
      name: `Prise de poste ${code}`,
      target_type: "PRE_SHIFT",
      items: [
        { key: "epi", label: "EPI portés (casque, gilet, chaussures)", critical: true },
        { key: "radio", label: "Radio testée", critical: false },
      ],
    },
  });
  expect(template.status()).toBe(201);

  // Réseau lent : la liste des sites arrive après l'ouverture du formulaire (cas observé en CI).
  await page.route("**/api/v1/sites?*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await uiLogin(page, account("DISPATCHER"));
  await page.goto("/hse/inspections");
  await page.getByRole("button", { name: "Réaliser une inspection" }).click();
  const form = page.getByRole("form", { name: "Réaliser une inspection" });
  await form.getByLabel("Checklist").selectOption({ label: `Prise de poste ${code} (Prise de poste, v1)` });
  await form.getByLabel("Résultat : EPI portés (casque, gilet, chaussures)").selectOption("NON_COMPLIANT");
  await form.getByLabel("Constat : EPI portés (casque, gilet, chaussures)").fill("Casque absent au briefing");
  // Le site se renseigne seul dès que la liste des sites arrive, même après l'ouverture du formulaire.
  await expect(form.getByRole("combobox", { name: "Site", exact: true })).not.toHaveValue("");
  await form.getByRole("button", { name: "Enregistrer l'inspection" }).click();
  const saved = page.getByRole("heading", { name: /INS-\d{6} enregistrée — Non conforme \(critique\)/ });
  await expect(saved).toBeVisible();
  const reference = (await saved.textContent())!.match(/INS-\d{6}/)![0];
  // Sans stockage privé ni antivirus configurés, aucune photo n'est acceptée (refus explicite).
  await page.getByLabel(/Ajouter une photo/).setInputFiles({
    name: "constat.png",
    mimeType: "image/png",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]),
  });
  await expect(page.getByRole("alert")).toContainText("momentanément");

  const hsePage = await (await browser.newContext({ locale: "fr-FR", timezoneId: "Africa/Conakry" })).newPage();
  await uiLogin(hsePage, hse);
  await hsePage.goto("/hse/inspections");
  await hsePage.getByRole("link", { name: reference }).click();
  await expect(hsePage.getByText("Casque absent au briefing")).toBeVisible();
  await hsePage.getByRole("button", { name: "Ajouter une action corrective" }).click();
  const action = hsePage.getByRole("form", { name: "Ajouter une action corrective" });
  await action.getByLabel("Action").fill("Rappel EPI et contrôle à l'entrée de fosse");
  await action.getByLabel("Responsable").selectOption({ index: 1 });
  await action.getByLabel("Échéance").fill("2099-01-31");
  await action.getByRole("button", { name: "Ajouter" }).click();
  await expect(hsePage.getByText("Rappel EPI et contrôle à l'entrée de fosse")).toBeVisible();
  await expect(hsePage.getByText("À réaliser")).toBeVisible();
});
