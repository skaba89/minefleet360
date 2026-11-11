import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Recette UI : zones de site (géofences) — création et désactivation par l'OPS_MANAGER depuis
// /flotte-gps/zones — puis politique d'alerte du site (limite de vitesse, perte de signal) et
// préférences personnelles de notification depuis /flotte-gps/alertes. Le DISPATCHER dispose de
// la lecture (et de la prise en compte d'alertes) mais ni de la gestion des zones ni de la
// politique du site : les deux refus sont vérifiés en UI et en API.

test("zones de site : création OPS_MANAGER depuis l'UI, lecture DISPATCHER sans gestion, désactivation", async ({ browser, page, request }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const opsAccount = account("OPS_MANAGER", dispatcher.workspace);
  const ops = await apiLogin(request, opsAccount);
  const sites = await (await request.get("/api/v1/sites", { headers: ops })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour OPS_MANAGER").toBeTruthy();
  const zoneCode = `ZONE-E2E-${suffix}`;
  const zoneName = `Zone E2E ${suffix}`;

  // 1. L'OPS_MANAGER crée une zone à partir de relevés terrain (une ligne « latitude, longitude » par sommet).
  await uiLogin(page, opsAccount);
  await page.goto("/flotte-gps/zones");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await page.getByRole("button", { name: "Nouvelle zone" }).click();
  await page.getByLabel("Code").fill(zoneCode);
  await page.getByLabel("Nom").fill(zoneName);
  await page
    .getByLabel("Sommets (une ligne « latitude, longitude » par sommet, 3 minimum)")
    .fill("10.4312, -12.7654\n10.4456, -12.7701\n10.4378, -12.7745");
  await page.getByRole("button", { name: "Enregistrer la zone" }).click();

  // La ligne apparaît avec le site, le code saisi et le nombre de sommets (anneau fermé : 3 + 1).
  const zoneRow = page.getByRole("row", { name: new RegExp(zoneName) });
  await expect(zoneRow).toContainText(`${siteInfo.code} — ${zoneCode} — 3 sommets`);
  await expect(page.getByRole("button", { name: "Nouvelle zone" })).toBeVisible();

  // 2. Contrôle croisé API : zone active, surface calculée, anneau fermé, bon site.
  const fences = await (
    await request.get("/api/v1/geofences", { headers: ops, params: { site_id: site } })
  ).json();
  const created = fences.find((g: { code: string }) => g.code === zoneCode);
  expect(created, "zone absente de la liste API").toBeTruthy();
  expect(created.site_id).toBe(site);
  expect(created.active).toBe(true);
  expect(created.area_m2).toBeGreaterThan(0);
  expect(created.coordinates).toHaveLength(4);

  // 3. Le DISPATCHER lit les zones du site mais ne dispose d'aucun bouton de gestion.
  const dispatcherContext = await browser.newContext();
  const dispatcherPage = await dispatcherContext.newPage();
  await uiLogin(dispatcherPage, dispatcher);
  await dispatcherPage.goto("/flotte-gps/zones");
  await dispatcherPage.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  await expect(dispatcherPage.getByRole("row", { name: new RegExp(zoneName) })).toBeVisible();
  await expect(dispatcherPage.getByRole("button", { name: "Nouvelle zone" })).toHaveCount(0);
  await dispatcherContext.close();
  const denied = await request.post("/api/v1/geofences", {
    headers: await apiLogin(request, dispatcher),
    data: { site_id: site, code: `ZONE-DENIED-${suffix}`, name: "Zone refusée", kind: "OTHER", coordinates: [[-12.76, 10.43], [-12.77, 10.44], [-12.77, 10.43]] },
  });
  expect(denied.status()).toBe(403);

  // 4. La désactivation retire la zone de la liste active mais la conserve consultable.
  await zoneRow.getByRole("button", { name: "Désactiver" }).click();
  await expect(page.getByRole("row", { name: new RegExp(zoneName) })).toHaveCount(0);
  const kept = await (
    await request.get("/api/v1/geofences", { headers: ops, params: { site_id: site, include_inactive: "true" } })
  ).json();
  const inactive = kept.find((g: { code: string }) => g.code === zoneCode);
  expect(inactive, "zone désactivée introuvable avec include_inactive").toBeTruthy();
  expect(inactive.active).toBe(false);
});

test("politique d'alerte du site et préférences de notification : réglages OPS_MANAGER, lisibilité DISPATCHER", async ({ browser, page, request }) => {
  test.setTimeout(120_000);
  const dispatcher = account("DISPATCHER");
  const site = await dispatcherSite(request, await apiLogin(request, dispatcher));
  const opsAccount = account("OPS_MANAGER", dispatcher.workspace);
  const ops = await apiLogin(request, opsAccount);
  const sites = await (await request.get("/api/v1/sites", { headers: ops })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour OPS_MANAGER").toBeTruthy();

  // 1. L'OPS_MANAGER règle la politique du site depuis l'UI : limite de vitesse + perte de signal.
  await uiLogin(page, opsAccount);
  await page.goto("/flotte-gps/alertes");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  const reglages = page.getByRole("region", { name: "Réglages d'alerte du site" });
  await reglages.getByLabel("Nouvelle limite (km/h, vide = aucune)").fill("60");
  await reglages.getByLabel("Perte de signal après (min, vide = non surveillée)").fill("20");
  await reglages.getByRole("button", { name: "Enregistrer" }).click();
  await expect(reglages.getByText(/Alerte au-delà de 60([.,]0)? km\/h mesurés/)).toBeVisible();
  await expect(reglages.getByText(/Perte de signal signalée après 20 min/)).toBeVisible();

  // 2. Contrôle croisé API : la politique est bien persistée pour ce site.
  const policy = await (await request.get(`/api/v1/sites/${site}/gps-policy`, { headers: ops })).json();
  expect(Number(policy.speed_limit_kmh)).toBe(60);
  expect(policy.signal_loss_minutes).toBe(20);

  // 3. Le DISPATCHER voit la politique appliquée mais ne dispose d'aucun formulaire de réglage.
  const dispatcherContext = await browser.newContext();
  const dispatcherPage = await dispatcherContext.newPage();
  await uiLogin(dispatcherPage, dispatcher);
  await dispatcherPage.goto("/flotte-gps/alertes");
  await dispatcherPage.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  const dispatcherReglages = dispatcherPage.getByRole("region", { name: "Réglages d'alerte du site" });
  await expect(dispatcherReglages.getByText(/Alerte au-delà de 60([.,]0)? km\/h mesurés/)).toBeVisible();
  await expect(dispatcherReglages.getByLabel("Nouvelle limite (km/h, vide = aucune)")).toHaveCount(0);
  const deniedPolicy = await request.put(`/api/v1/sites/${site}/gps-policy`, {
    headers: await apiLogin(request, dispatcher),
    data: { speed_limit_kmh: "30" },
  });
  expect(deniedPolicy.status()).toBe(403);

  // 4. Préférences personnelles de notification : choix e-mail enregistré et relu par l'API.
  const notifications = page.getByRole("region", { name: "Mes notifications d'alertes" });
  await notifications.getByRole("checkbox", { name: "Par e-mail" }).check();
  await notifications.getByRole("button", { name: "Enregistrer mes choix" }).click();
  await expect(notifications.getByText("Choix enregistrés.")).toBeVisible();
  const prefs = await (await request.get("/api/v1/me/alert-notifications", { headers: ops })).json();
  expect(prefs.email_enabled).toBe(true);
  expect(prefs.sms_enabled).toBe(false);
  await dispatcherContext.close();
});
