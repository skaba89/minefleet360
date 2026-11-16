import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, type Account } from "../e2e/fixtures";

/**
 * Inspection HSE sans réseau (phase 3, tranche 2) : coupure en cours de session, file IndexedDB réelle,
 * service worker réel, synchronisation unique acquittée par le serveur (Idempotency-Key, PR #457).
 * L'ouverture de l'application sans réseau pour une inspection relève de la tranche suivante.
 */
const performer = () => account("DISPATCHER");

/** Modèle de checklist fictif propre au test, créé par le compte HSE (hse.checklist.manage). */
async function createTemplate(request: APIRequestContext): Promise<string> {
  const headers = await apiLogin(request, account("HSE"));
  const code = `E2E-${Date.now()}`;
  const resp = await request.post("/api/v1/hse/checklist-templates", {
    headers,
    data: {
      code,
      name: `Prise de poste ${code}`,
      target_type: "PRE_SHIFT",
      items: [
        { key: "epi", label: "EPI portés", critical: true },
        { key: "radio", label: "Radio testée", critical: false },
      ],
    },
  });
  expect(resp.status()).toBe(201);
  return `Prise de poste ${code}`;
}

async function inspectionsNoted(request: APIRequestContext, note: string): Promise<number> {
  const headers = await apiLogin(request, account("HSE"));
  const resp = await request.get("/api/v1/hse/inspections", { headers, params: { page_size: 200 } });
  expect(resp.status()).toBe(200);
  const items = (await resp.json()).items as { note: string | null }[];
  return items.filter((i) => i.note === note).length;
}

async function uiLogin(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
}

async function openInspections(page: Page): Promise<void> {
  const menu = page.getByRole("button", { name: "Afficher le menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: "Sécurité (HSE)" }).click();
  await page.getByRole("link", { name: "Inspections et checklists" }).click();
  await expect(page.getByRole("heading", { name: "Inspections" })).toBeVisible();
}

/** Ouvre le formulaire et choisit la checklist (chargée en ligne, avant toute coupure). */
async function startInspection(page: Page, templateName: string): Promise<void> {
  await page.getByRole("button", { name: "Réaliser une inspection" }).click();
  const checklist = page.getByLabel("Checklist");
  await expect(checklist.locator("option", { hasText: templateName })).toHaveCount(1);
  await checklist.selectOption({ label: `${templateName} (Prise de poste, v1)` });
  await expect(page.getByLabel("Résultat : EPI portés")).toBeVisible();
}

/**
 * Le clic d'envoi peut tomber pendant une re-renderisation (cf. hse-offline.spec.ts) : la fermeture du
 * formulaire prouve la prise en compte ; sinon on recommence, la note unique permet de compter les doublons.
 */
async function submitUntilClosed(page: Page, note: string, submit: string): Promise<void> {
  const form = page.getByRole("form", { name: /Réaliser une inspection/ });
  await page.getByLabel("Observation générale (facultatif)").fill(note);
  await page.getByRole("button", { name: submit }).click();
  try {
    await expect(form).toBeHidden({ timeout: 3_000 });
  } catch {
    await page.getByRole("button", { name: submit }).click();
    await expect(form).toBeHidden();
  }
}

test("inspection sans réseau, synchronisée une seule fois au retour du réseau", async ({ page, context, request }) => {
  const templateName = await createTemplate(request);
  const note = `Inspection hors ligne ${Date.now()}`;
  await uiLogin(page, performer());
  await openInspections(page);
  await startInspection(page, templateName);
  await context.setOffline(true);
  await expect(page.getByRole("button", { name: "Enregistrer sur l'appareil" })).toBeVisible();
  await submitUntilClosed(page, note, "Enregistrer sur l'appareil");
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText(`Inspection — ${templateName} v1`)).toBeVisible();
  await expect(queue.getByText("En attente de synchronisation")).toBeVisible();
  expect(await inspectionsNoted(request, note)).toBe(0);

  await context.setOffline(false);
  await expect(queue.getByText(/Synchronisé — INS-\d{6}/)).toBeVisible({ timeout: 20_000 });
  expect(await inspectionsNoted(request, note)).toBe(1);
  // Nouvelle passe après rechargement : rien n'est renvoyé.
  await page.reload();
  await expect(page.getByText(/Synchronisé — INS-\d{6}/)).toBeVisible();
  expect(await inspectionsNoted(request, note)).toBe(1);
});

test("réponse perdue : l'inspection créée n'est pas dupliquée au rejeu", async ({ page, request }) => {
  const templateName = await createTemplate(request);
  const note = `Inspection réponse perdue ${Date.now()}`;
  await uiLogin(page, performer());
  await openInspections(page);
  let dropped = false;
  await page.route("**/api/v1/hse/inspections", async (route) => {
    if (route.request().method() === "POST" && !dropped) {
      dropped = true;
      await route.fetch(); // le serveur crée l'inspection…
      await route.abort("connectionreset"); // …mais la réponse n'arrive jamais
      return;
    }
    await route.continue();
  });
  await startInspection(page, templateName);
  await submitUntilClosed(page, note, "Enregistrer l'inspection");
  await expect(page.getByText(/Synchronisé — INS-\d{6}/)).toBeVisible({ timeout: 20_000 });
  expect(dropped).toBe(true);
  expect(await inspectionsNoted(request, note)).toBe(1);
});
