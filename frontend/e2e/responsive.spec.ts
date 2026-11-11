import { expect, test, type Page } from "@playwright/test";

import { account, apiLogin, type Account } from "./fixtures";

/**
 * Écrans à la largeur d'un téléphone d'entrée de gamme (360 px) : aucune barre de défilement horizontale de la
 * page, aucun élément interactif hors de l'écran, cibles tactiles d'au moins 32 px de haut. Les tableaux larges
 * défilent dans leur propre conteneur.
 */
const VIEWPORTS = [
  { name: "téléphone 360 px", width: 360, height: 740, touch: true },
  { name: "tablette 768 px", width: 768, height: 1024, touch: true },
];

const ROUTES: Record<string, string[]> = {
  OPS_MANAGER: ["/", "/vehicules", "/flotte-gps", "/flotte-gps/zones", "/conducteurs", "/affectations", "/missions",
    "/atelier", "/atelier/fiabilite", "/maintenance", "/carburant", "/pieces", "/pneus", "/hse", "/hse/inspections",
    "/couts", "/pesees", "/indicateurs", "/mon-compte/securite"],
  HSE: ["/hse", "/hse/inspections", "/hse/checklists"],
  TENANT_ADMIN: ["/administration/sites", "/administration/utilisateurs", "/administration/journal",
    "/administration/lieux-matieres", "/administration/documents-exiges", "/juridique"],
  FINANCE: ["/couts"],
};

const OPEN_FORMS: Record<string, [string, string][]> = {
  OPS_MANAGER: [["/hse", "Déclarer un incident"], ["/hse/inspections", "Réaliser une inspection"], ["/atelier", "Signaler une panne"]],
  HSE: [["/hse/checklists", "Nouveau modèle ou nouvelle version"], ["/flotte-gps/zones", "Nouvelle zone"]],
  TENANT_ADMIN: [["/administration/sites", "Nouveau site"]],
  FINANCE: [],
};

const DETAILS: Record<string, [string, string][]> = {
  OPS_MANAGER: [["/vehicules", "/vehicules/"], ["/pneus", "/pneus/"],
    ["/hse", "/hse/"], ["/conducteurs", "/conducteurs/"]],
  HSE: [["/hse/inspections", "/hse/inspections/"]],
};

async function login(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("button", { name: "Se déconnecter" })).toBeVisible();
}

interface Problem {
  kind: string;
  detail: string;
}

async function audit(page: Page, touchTargets: boolean): Promise<Problem[]> {
  return page.evaluate((touchTargets) => {
    const problems: { kind: string; detail: string }[] = [];
    const width = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > width + 1) {
      problems.push({ kind: "page", detail: `largeur ${document.documentElement.scrollWidth} > ${width}` });
    }
    const describe = (el: Element) =>
      `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${(el.getAttribute("class") ?? "").split(" ")[0]} « ${(el.textContent ?? "").trim().slice(0, 40)} »`;
    const scrollsInside = (el: Element) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const style = getComputedStyle(p);
        if (["auto", "scroll"].includes(style.overflowX) && p.scrollWidth > p.clientWidth) return true;
      }
      return false;
    };
    // Les marqueurs de la carte flotte vivent dans un canvas panable/zoomable (MapLibre) : selon le
    // cadrage, un pin peut déborder du viewport sans être un défaut de mise en page.
    const inPannableMap = (el: Element) => el.closest(".fleet-map-canvas") !== null;
    for (const el of Array.from(document.querySelectorAll("button, a, input, select, textarea"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0 || getComputedStyle(el).visibility === "hidden") continue;
      if (r.right > width + 1 && !scrollsInside(el) && !inPannableMap(el)) problems.push({ kind: "hors-écran", detail: describe(el) });
      const type = el.getAttribute("type") ?? "";
      const control = ["BUTTON", "SELECT", "TEXTAREA"].includes(el.tagName) ||
        (el.tagName === "INPUT" && !["checkbox", "radio", "file", "hidden"].includes(type));
      const navLink = el.tagName === "A" && el.closest(".mainnav") !== null;
      if (touchTargets && (control || navLink) && r.height < 44) {
        problems.push({ kind: "cible<44px", detail: `${describe(el)} (${Math.round(r.height)} px)` });
      }
      if (touchTargets && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName) && control && parseFloat(getComputedStyle(el).fontSize) < 16) {
        problems.push({ kind: "zoom-iOS", detail: `${describe(el)} (${getComputedStyle(el).fontSize})` });
      }
    }
    return problems;
  }, touchTargets);
}

for (const viewport of VIEWPORTS) {
  test.describe(viewport.name, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height }, isMobile: true, hasTouch: viewport.touch });
    for (const [role, routes] of Object.entries(ROUTES)) {
  test(`écrans ${role}`, async ({ page, request }) => {
    test.setTimeout(240_000);
    // Cibles tactiles et zoom iOS vérifiés au format téléphone ; débordements à toutes les largeurs.
    const touchTargets = viewport.width <= 700;
    const checked: string[] = [];
    const a = account(role);
    await apiLogin(request, a);
    await login(page, a);
    const report: string[] = [];
    const check = async (name: string) => {
      // Certaines pages s'actualisent en continu : réseau « au repos » attendu au plus 5 s.
      await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
      checked.push(name);
      for (const p of await audit(page, touchTargets)) report.push(`${name} [${p.kind}] ${p.detail}`);
    };
    for (const route of routes) {
      await page.goto(route);
      await check(route);
    }
    // Menu déplié, formulaires ouverts et fiches détaillées (premier élément de chaque liste).
    await page.goto("/");
    await page.getByRole("button", { name: "Afficher le menu" }).click();
    await check("menu déplié");
    for (const [route, button] of OPEN_FORMS[role] ?? []) {
      await page.goto(route);
      await page.getByRole("button", { name: button }).first().click();
      await check(`${route} + « ${button} »`);
    }
    for (const [route, linkPattern] of DETAILS[role] ?? []) {
      await page.goto(route);
      const link = page.locator(`main a[href^="${linkPattern}"]`).first();
      await expect(link, `aucune fiche à ouvrir depuis ${route}`).toBeVisible();
      await link.click();
      await check(`${route} → fiche`);
    }
    expect(report, report.join("\n")).toEqual([]);
    // Garde-fou : formulaires et fiches réellement ouverts (pas d'écran sauté silencieusement).
    const extra = (OPEN_FORMS[role]?.length ?? 0) + (DETAILS[role]?.length ?? 0);
    expect(checked.length).toBe(routes.length + 1 + extra);
  });
    }
  });
}
