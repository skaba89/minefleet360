import { readFileSync } from "node:fs";

import { expect, type Page } from "@playwright/test";

export interface DemoAccount {
  tenant: string;
  role: string;
  site: string | null;
  email: string;
  password: string;
}

/** Identifiants DEMO (fichier tabulé de `minefleet demo seed` : société, rôle, site, e-mail, mot de passe). */
export function demoAccounts(): DemoAccount[] {
  const path = process.env.MF_DEMO_ACCOUNTS;
  if (!path)
    throw new Error(
      "MF_DEMO_ACCOUNTS doit désigner le fichier d'identifiants DEMO (sortie du seed).",
    );
  return readFileSync(path, "utf-8")
    .split(/\r?\n/)
    .filter(
      (line) => line && !line.startsWith("#") && !line.startsWith("societe\t"),
    )
    .map((line) => line.split("\t"))
    .filter((parts) => parts.length === 5)
    .map(([tenant, role, site, email, password]) => ({
      tenant: tenant!,
      role: role!,
      site: site === "-" ? null : site!,
      email: email!,
      password: password!,
    }));
}

export function demo(
  role: string,
  tenant = "demo-bauxite",
  site: string | null = null,
): DemoAccount {
  const found = demoAccounts().find(
    (a) => a.tenant === tenant && a.role === role && a.site === site,
  );
  if (!found)
    throw new Error(
      `Compte DEMO introuvable : ${tenant} ${role} ${site ?? ""}`,
    );
  return found;
}

export async function login(page: Page, a: DemoAccount): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.tenant);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(
    page.getByRole("navigation", { name: "Navigation principale" }),
  ).toBeVisible();
}

export async function open(page: Page, menu: string): Promise<void> {
  await page
    .getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: menu, exact: true })
    .click();
}

/**
 * Compte PLATFORM_ADMIN de recette : MF_PLATFORM_ACCOUNT désigne un fichier tabulé
 * « e-mail<tab>mot de passe » (écrit par le workflow depuis MF_BOOTSTRAP_PASSWORD).
 * Absent du jeu DEMO : le test concerné saute.
 */
export function platformAccount(): { email: string; password: string } | null {
  const path = process.env.MF_PLATFORM_ACCOUNT;
  if (!path) return null;
  const line = readFileSync(path, "utf-8").trim();
  const parts = line.split("\t");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    throw new Error(
      "MF_PLATFORM_ACCOUNT doit être un fichier tabulé « e-mail<tab>mot de passe ».",
    );
  }
  return { email: parts[0]!, password: parts[1]! };
}

export async function loginPlatform(
  page: Page,
  a: { email: string; password: string },
): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill("mf-platform");
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(
    page.getByRole("navigation", { name: "Navigation principale" }),
  ).toBeVisible();
}
