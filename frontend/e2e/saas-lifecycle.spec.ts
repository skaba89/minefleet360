import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { uiPlatformLogin } from "./fixtures";

// Recette UI du cycle SaaS complet (phase 2 de la feuille de route commercialisation) :
// plan tarifé → société → abonnement actif → facture émise → support plateforme →
// onboarding de la société (checklist calculée) → quota appliqué à la borne →
// facture lue par la société → export réversibilité.
// Données 100 % fictives, créées par le test ; e-mails d'invitation lus dans le
// répertoire de capture (adaptateur « capture » uniquement — jamais en SMTP) ;
// mots de passe éphémères, jamais commités.

const MAIL_DIR = process.env.MF_MAIL_CAPTURE_DIR ?? "/tmp/minefleet-e2e-mail";

/** Dernier e-mail d'invitation capturé pour le destinataire : jeton du lien d'activation. */
function activationTokenFor(email: string): string {
  const names = readdirSync(MAIL_DIR).filter((name) => name.endsWith(".json")).sort().reverse();
  for (const name of names) {
    const mail = JSON.parse(readFileSync(join(MAIL_DIR, name), "utf-8")) as {
      to: string;
      kind: string;
      body: string;
    };
    if (mail.to === email && mail.kind === "INVITATION") {
      // Jeton composé « tenant.record.secret » : URL-safe (lettres, chiffres, point, tiret, tiret bas).
      const match = /\/activation#token=([A-Za-z0-9_.-]+)/.exec(mail.body);
      if (match) return match[1]!;
    }
  }
  throw new Error(`Aucun e-mail d'invitation capturé pour ${email} dans ${MAIL_DIR}`);
}

async function expectInvitation(email: string): Promise<string> {
  let token: string | null = null;
  await expect
    .poll(
      () => {
        try {
          token = activationTokenFor(email);
        } catch {
          token = null;
        }
        return token;
      },
      { timeout: 10_000, intervals: [500, 1_000] },
    )
    .toBeTruthy();
  if (token === null) throw new Error(`Jeton d'activation introuvable pour ${email}`);
  return token;
}

/** Active un compte invité depuis son e-mail capturé, puis rend la main sur l'écran de succès. */
async function activateAccount(page: Page, email: string, password: string): Promise<void> {
  const token = await expectInvitation(email);
  await page.goto(`/activation#token=${token}`);
  await page.getByLabel("Nouveau mot de passe (12 caractères minimum)").fill(password);
  await page.getByLabel("Confirmer le mot de passe").fill(password);
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Votre compte est activé.")).toBeVisible();
}

/** Montants GNF affichés : le séparateur de milliers fr-FR varie selon l'ICU du navigateur. */
function gnf(amount: string): RegExp {
  return new RegExp(amount.split(" ").join("[\\s\\u00a0\\u202f]*") + "[\\s\\u00a0\\u202f]*GNF");
}

test("cycle SaaS complet : plan tarifé, société, abonnement, facture, support, onboarding, quota, export", async ({ page }) => {
  test.setTimeout(300_000);
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const planCode = `E2E_SAAS_${suffix}`;
  const planName = "Formule E2E SaaS";
  const tenantCode = `e2e-saas-${suffix.toLowerCase()}`;
  const displayName = `Société SaaS E2E ${suffix}`;
  const adminEmail = `admin.saas.${suffix.toLowerCase()}@exemple.mf`;
  const opsEmail = `ops.saas.${suffix.toLowerCase()}@exemple.mf`;
  const adminPassword = `Fictif-SaaS-${suffix}-Aa1!`;
  const opsPassword = `Fictif-Atelier-${suffix}-Aa1!`;
  let invoiceNumber = "";

  // --- 1. Plan SaaS tarifé et borné (UI plateforme) ----------------------------------------------
  await uiPlatformLogin(page);
  await page.goto("/plateforme/plans");
  await page.getByRole("button", { name: "Créer un plan" }).click();
  const planForm = page.getByRole("form", { name: "Créer un plan SaaS" });
  await planForm.getByLabel(/Code \(majuscules/).fill(planCode);
  await planForm.getByLabel("Nom affiché").fill(planName);
  await planForm.getByLabel(/Quota utilisateurs/).fill("5");
  await planForm.getByLabel(/Quota sites/).fill("1");
  await planForm.getByLabel(/Quota véhicules/).fill("3");
  await planForm.getByLabel(/Quota traceurs GPS/).fill("2");
  await planForm.getByLabel(/Rétention des documents/).fill("365");
  await planForm.getByLabel(/Tarif mensuel en GNF/).fill("1500000");
  await planForm.getByLabel(/Période de facturation/).selectOption({ value: "MONTHLY" });
  await planForm.getByLabel("Statut").selectOption({ label: "Actif" });
  await planForm.getByRole("button", { name: "Créer", exact: true }).click();
  const planRow = page.getByRole("row", { name: new RegExp(planCode) });
  await expect(planRow).toContainText("Actif");
  await expect(planRow).toContainText(gnf("1 500 000"));

  // --- 2. Société cliente (invitation du premier administrateur) ---------------------------------
  await page.goto("/plateforme/nouvelle-societe");
  const tenantForm = page.getByRole("form", { name: "Informations de la société" });
  await tenantForm.getByLabel("Code unique (minuscules et tirets)").fill(tenantCode);
  await tenantForm.getByLabel("Raison sociale").fill(`${displayName} SARL fictive`);
  await tenantForm.getByLabel("Nom affiché").fill(displayName);
  await tenantForm.getByLabel("E-mail du premier administrateur").fill(adminEmail);
  await tenantForm.getByLabel("Nom du premier administrateur").fill("Admin SaaS E2E");
  await tenantForm.getByRole("button", { name: "Créer et inviter" }).click();
  await expect(page).toHaveURL(/\/plateforme\/societes$/);
  await expect(page.getByRole("row", { name: new RegExp(tenantCode) })).toContainText("Active");

  // --- 3. Abonnement : essai daté puis activation ------------------------------------------------
  await page.goto("/plateforme/abonnements");
  await page.getByRole("button", { name: "Souscrire un abonnement" }).click();
  await page.getByLabel("Société cliente").selectOption({ label: `${tenantCode} — ${displayName}` });
  await page.getByLabel("Plan (actifs uniquement)").selectOption({ label: `${planCode} — ${planName}` });
  await page.getByRole("button", { name: "Souscrire", exact: true }).click();
  // Le filtre de la page montre l'abonnement de la société : essai, puis activation.
  // On attend la fermeture du formulaire (sync), puis le filtre (dernier « Société » du DOM, après le formulaire).
  await expect(page.getByRole("form", { name: "Souscrire un abonnement" })).toHaveCount(0);
  await page.getByLabel("Société").last().selectOption({ label: `${tenantCode} — ${displayName}` });
  const subscriptionRow = page.getByRole("row", { name: new RegExp(planCode) });
  await expect(subscriptionRow).toContainText("Essai");
  await subscriptionRow.getByRole("button", { name: "Activer", exact: true }).click();
  await page.getByRole("form", { name: `Activer l'essai de ${planCode}` })
    .getByRole("button", { name: "Confirmer" })
    .click();
  await expect(subscriptionRow).toContainText("Actif");

  // --- 4. Facture d'abonnement : DRAFT préremplie depuis le tarif du plan, puis émission ---------
  await page.goto("/plateforme/facturation");
  await page.getByRole("button", { name: "Créer une facture" }).click();
  await page.getByLabel("Société cliente").selectOption({ label: `${tenantCode} — ${displayName}` });
  await page
    .getByLabel(/Abonnement \(facultatif/)
    .selectOption({ label: `${planCode} — Actif` });
  await page.getByLabel(/Taxe \(points de base/).fill("1800");
  await page.getByRole("button", { name: "Créer la facture" }).click();
  // La liste exige la sélection de la société dans le filtre de la page (après fermeture du formulaire).
  await expect(page.getByRole("form", { name: "Créer une facture (brouillon)" })).toHaveCount(0);
  await page.getByLabel("Société").last().selectOption({ label: `${tenantCode} — ${displayName}` });
  const invoiceRow = page.getByRole("row", { name: /MF-\d{4}-\d{5}/ });
  await expect(invoiceRow).toContainText("Brouillon");
  await expect(invoiceRow).toContainText(gnf("1 770 000")); // 1 500 000 + 18 %
  invoiceNumber = (await invoiceRow.textContent())!.match(/MF-\d{4}-\d{5}/)![0]!;
  await invoiceRow.getByRole("button", { name: "Émettre", exact: true }).click();
  await page.getByRole("form", { name: `Émettre la facture ${invoiceNumber} (figer le document)` })
    .getByRole("button", { name: "Confirmer" })
    .click();
  await expect(invoiceRow).toContainText("Émise");
  // Détail figé : ligne d'abonnement, taxe 18 %, total.
  await invoiceRow.getByRole("button", { name: invoiceNumber }).click();
  const detail = page.getByRole("table").filter({ hasText: `Détail de la facture ${invoiceNumber}` });
  await expect(detail).toContainText(`Abonnement MineFleet 360 — plan ${planName} (${planCode})`);
  await expect(detail).toContainText("Taxe (18 %)");
  await expect(detail).toContainText(gnf("1 770 000"));

  // --- 5. Support plateforme : vue consolidée du compte -------------------------------------------
  await page.goto("/plateforme/support");
  await page.getByLabel("Société").last().selectOption({ label: `${displayName} (${tenantCode})` });
  await expect(page.getByText("Usage face aux limites du plan")).toBeVisible();
  await expect(page.getByText(`${planName} — Actif`)).toBeVisible();
  await expect(page.getByText("0 actifs, 1 en attente, 0 désactivés")).toBeVisible(); // admin non activé
  const recentInvoiceRow = page.getByRole("row", { name: new RegExp(invoiceNumber) });
  await expect(recentInvoiceRow).toContainText("Émise");

  // --- 6. Activation du compte administrateur de la société --------------------------------------
  await activateAccount(page, adminEmail, adminPassword);
  // La session plateforme encore active redirigerait /connexion vers l'accueil : on repart d'un contexte vierge.
  await page.context().clearCookies();
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(tenantCode);
  await page.getByLabel("Adresse e-mail").fill(adminEmail);
  await page.getByLabel("Mot de passe").fill(adminPassword);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeVisible();

  // --- 7. Checklist de démarrage : l'abonnement seul est constaté (1/5) ---------------------------
  await page.goto("/demarrage");
  await expect(page.getByText("1/5 étapes réalisées (20 %)")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Progression du démarrage" })).toHaveAttribute(
    "aria-valuenow",
    "20",
  );

  // --- 8. Premier site, puis refus du deuxième à la borne du plan (quota) ------------------------
  await page.goto("/administration/sites");
  await page.getByRole("button", { name: "Nouveau site" }).click();
  await page.getByLabel("Code (unique, définitif)").fill("SITE-S1");
  await page.getByLabel("Nom", { exact: true }).fill("Site E2E SaaS");
  await page.getByRole("button", { name: "Créer le site" }).click();
  await expect(page.getByRole("row", { name: /SITE-S1/ })).toContainText("Actif");
  await page.goto("/demarrage");
  await expect(page.getByText("2/5 étapes réalisées (40 %)")).toBeVisible();
  await page.goto("/administration/sites");
  await page.getByRole("button", { name: "Nouveau site" }).click();
  await page.getByLabel("Code (unique, définitif)").fill("SITE-S2");
  await page.getByLabel("Nom", { exact: true }).fill("Site au-delà de la borne");
  await page.getByRole("button", { name: "Créer le site" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "La limite de votre formule est atteinte : changez de formule ou libérez de la place.",
  );
  await page.getByRole("button", { name: "Annuler" }).click();

  // --- 9. Invitation d'un collègue puis activation (étape « équipe » de la checklist) -------------
  await page.goto("/administration/utilisateurs");
  await page.getByRole("button", { name: "Inviter un utilisateur" }).click();
  await page.getByLabel("Adresse e-mail").fill(opsEmail);
  await page.getByLabel("Nom affiché").fill("Opérations E2E");
  await page.getByLabel("Rôle").selectOption({ value: "OPS_MANAGER" }); // portée TENANT autorisée
  await page.getByRole("button", { name: "Envoyer l'invitation" }).click();
  await expect(page.getByRole("row", { name: /Opérations E2E/ })).toContainText("Invité");
  await activateAccount(page, opsEmail, opsPassword);

  // --- 10. Premier véhicule ------------------------------------------------------------------------
  await page.goto("/vehicules");
  await page.getByRole("button", { name: "Nouveau véhicule" }).click();
  const vehicleForm = page.getByRole("form", { name: "Nouveau véhicule" });
  await expect(vehicleForm.getByLabel("Catégorie").locator("option").nth(1)).toBeAttached(); // catalogue copié
  await vehicleForm.getByLabel("Catégorie").selectOption({ index: 1 });
  await vehicleForm.getByLabel("N° de parc (unique, définitif)").fill(`E2E-SAAS-${suffix}`);
  await vehicleForm.getByRole("button", { name: "Créer le véhicule" }).click();
  await expect(page).toHaveURL(/\/vehicules\/[0-9a-f-]{36}$/);

  // --- 11. Traceur GPS associé au véhicule --------------------------------------------------------
  await page.getByLabel("Identifiant du traceur").fill(`E2E-TRK-${suffix}`);
  await page.getByRole("button", { name: "Associer un traceur" }).click();
  await expect(page.getByText(`Traceur associé : E2E-TRK-${suffix}`)).toBeVisible();

  // --- 12. Checklist complète : 5/5, toutes les étapes constatées depuis l'état réel --------------
  await page.goto("/demarrage");
  await expect(page.getByText("5/5 étapes réalisées (100 %)")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Progression du démarrage" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );

  // --- 13. La société voit son abonnement, sa facture et télécharge son export --------------------
  await page.goto("/abonnement");
  await expect(page.getByText(`Formule E2E SaaS (${planCode})`)).toBeVisible();
  await expect(page.getByText("Actif", { exact: true }).first()).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter les données (JSON)" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.json$/);
  const exportPath = await download.path();
  const exported = JSON.parse(readFileSync(exportPath!, "utf-8")) as {
    tenant: { code: string };
    sites: Array<{ code: string }>;
    users: Array<{ email: string | null }>;
    vehicles: Array<{ fleet_number: string }>;
    invoices: Array<{ number: string; status: string }>;
  };
  expect(exported.tenant.code).toBe(tenantCode);
  expect(exported.sites.map((site) => site.code)).toContain("SITE-S1");
  expect(exported.vehicles.map((vehicle) => vehicle.fleet_number)).toContain(`E2E-SAAS-${suffix}`);
  expect(exported.invoices.some((invoice) => invoice.number === invoiceNumber && invoice.status === "ISSUED")).toBe(true);
  // Aucun secret d'authentification dans l'export (règle lot 4).
  expect(JSON.stringify(exported)).not.toMatch(/password|password_hash|mfa_secret/i);

  await page.goto("/factures");
  const ownInvoiceRow = page.getByRole("row", { name: new RegExp(invoiceNumber) });
  await expect(ownInvoiceRow).toContainText("Émise");
  await expect(ownInvoiceRow).toContainText(gnf("1 770 000"));
});
