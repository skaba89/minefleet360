import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { account, apiLogin, type Account } from "../e2e/fixtures";

/**
 * Déclaration d'incident HSE sans réseau, de bout en bout : file IndexedDB réelle, service worker réel,
 * coupure simulée par le navigateur, synchronisation unique acquittée par le serveur.
 */
const dispatcher = () => account("DISPATCHER");

async function incidentsTitled(request: APIRequestContext, title: string): Promise<number> {
  const headers = await apiLogin(request, account("HSE"));
  const resp = await request.get("/api/v1/hse/incidents", { headers, params: { page_size: 200 } });
  expect(resp.status()).toBe(200);
  const items = (await resp.json()).items as { title: string }[];
  return items.filter((i) => i.title === title).length;
}

/** Connexion valable sur écran étroit (menu replié) comme sur poste de travail. */
async function uiLogin(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
}

async function declare(page: Page, title: string, submit: string): Promise<void> {
  const form = page.getByRole("form", { name: /Déclarer un incident/ });
  if (!(await form.isVisible())) {
    await page.getByRole("button", { name: /Déclarer (un|un autre) incident/ }).first().click();
  }
  await page.getByLabel("Titre").fill(title);
  await page.getByLabel("Description des faits").fill("Constat fictif saisi pendant une coupure réseau.");
  await page.getByRole("button", { name: submit }).click();
}

/**
 * Le clic d'envoi peut tomber pendant une re-renderisation React et ne jamais déclencher la soumission
 * (événement perdu sur un noeud remplacé : formulaire toujours affiché, aucun appel, aucune erreur).
 * La fermeture du formulaire est la preuve que la soumission a été prise en compte ; sinon on recommence.
 */
async function declareUntilClosed(page: Page, title: string, submit: string): Promise<void> {
  await declare(page, title, submit);
  const form = page.getByRole("form", { name: /Déclarer un incident/ });
  try {
    await expect(form).toBeHidden({ timeout: 3_000 });
  } catch {
    await declare(page, title, submit);
  }
}

async function openHse(page: Page): Promise<void> {
  const menu = page.getByRole("button", { name: "Afficher le menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: "Sécurité (HSE)" }).click();
  await expect(page.getByRole("heading", { name: "Sécurité (HSE)" })).toBeVisible();
}

async function waitForServiceWorker(page: Page): Promise<void> {
  // ready indique qu'un worker est actif, pas que cet onglet est contrôlé ni que
  // le shell de production est entièrement disponible en cache hors réseau.
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  await page.waitForFunction(async () => {
    if (!navigator.serviceWorker.controller) return false;
    const shell = await caches.match("/index.html");
    const raw = localStorage.getItem("minefleet-field-profile-v1");
    if (!shell || !raw) return false;
    try {
      const profile = JSON.parse(raw) as { sites?: unknown[] };
      return Array.isArray(profile.sites) && profile.sites.length > 0;
    } catch {
      return false;
    }
  }, undefined, { timeout: 20_000 });
}

test("déclaration sans réseau, synchronisée une seule fois au retour du réseau", async ({ page, context, request }) => {
  const title = `Hors ligne ${Date.now()}`;
  await uiLogin(page, dispatcher());
  await openHse(page);
  await context.setOffline(true);
  await declareUntilClosed(page, title, "Enregistrer sur l'appareil");
  const queue = page.getByRole("region", { name: "Déclarations saisies sur cet appareil" });
  await expect(queue.getByText("En attente de synchronisation")).toBeVisible();
  expect(await incidentsTitled(request, title)).toBe(0);

  await context.setOffline(false);
  await expect(queue.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible({ timeout: 20_000 });
  expect(await incidentsTitled(request, title)).toBe(1);
  // Nouvelle passe : rien n'est renvoyé.
  await page.reload();
  await expect(page.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible();
  expect(await incidentsTitled(request, title)).toBe(1);
});

test("réponse perdue : l'incident créé n'est pas dupliqué au rejeu", async ({ page, request }) => {
  const title = `Réponse perdue ${Date.now()}`;
  await uiLogin(page, dispatcher());
  await openHse(page);
  let dropped = false;
  await page.route("**/api/v1/hse/incidents", async (route) => {
    if (route.request().method() === "POST" && !dropped) {
      dropped = true;
      await route.fetch(); // le serveur traite la requête…
      await route.abort("connectionreset"); // …mais la réponse n'arrive jamais
      return;
    }
    await route.continue();
  });
  await declareUntilClosed(page, title, "Enregistrer la déclaration");
  await expect(page.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible({ timeout: 20_000 });
  expect(dropped).toBe(true);
  expect(await incidentsTitled(request, title)).toBe(1);
});

test("deux onglets reconnectés ensemble n'envoient qu'une fois", async ({ context, request }) => {
  const title = `Deux onglets ${Date.now()}`;
  const first = await context.newPage();
  await uiLogin(first, dispatcher());
  await openHse(first);
  await context.setOffline(true);
  await declare(first, title, "Enregistrer sur l'appareil");
  await expect(first.getByText("En attente de synchronisation")).toBeVisible();
  const second = await context.newPage();
  await context.setOffline(false);
  await second.goto("/hse");
  await expect(second.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible({ timeout: 20_000 });
  await expect(first.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible({ timeout: 40_000 });
  expect(await incidentsTitled(request, title)).toBe(1);
});

test("ouverture de l'application sans réseau puis reconnexion", async ({ page, context, request }) => {
  const title = `Démarrage hors ligne ${Date.now()}`;
  await uiLogin(page, dispatcher());
  await openHse(page); // mémorise le profil terrain (sites déclarables)
  await waitForServiceWorker(page);
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: /mode hors ligne/ })).toBeVisible();
  await declare(page, title, "Enregistrer sur l'appareil");
  await expect(page.getByText("En attente de synchronisation", { exact: true })).toBeVisible();
  await context.setOffline(false);
  // Session rétablie par le cookie de rafraîchissement, puis synchronisation depuis l'écran HSE.
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible({ timeout: 20_000 });
  await openHse(page);
  await expect(page.getByText(/Synchronisé — HSE-\d{6}/)).toBeVisible({ timeout: 20_000 });
  expect(await incidentsTitled(request, title)).toBe(1);
});

test("la déconnexion volontaire prévient puis efface la file locale", async ({ page, context }) => {
  await uiLogin(page, dispatcher());
  await openHse(page);
  await context.setOffline(true);
  await declare(page, `Non envoyée ${Date.now()}`, "Enregistrer sur l'appareil");
  await expect(page.getByText("En attente de synchronisation")).toBeVisible();
  let warned = "";
  page.once("dialog", async (dialog) => {
    warned = dialog.message();
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect.poll(() => warned).toContain("ne sont pas encore synchronisées");
  await expect(page.getByText("En attente de synchronisation")).toBeVisible();
  await context.setOffline(false);
});

