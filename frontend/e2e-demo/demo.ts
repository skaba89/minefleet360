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
  if (!path) throw new Error("MF_DEMO_ACCOUNTS doit désigner le fichier d'identifiants DEMO (sortie du seed).");
  return readFileSync(path, "utf-8")
    .split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("societe\t"))
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

export function demo(role: string, tenant = "demo-bauxite", site: string | null = null): DemoAccount {
  const found = demoAccounts().find((a) => a.tenant === tenant && a.role === role && a.site === site);
  if (!found) throw new Error(`Compte DEMO introuvable : ${tenant} ${role} ${site ?? ""}`);
  return found;
}

export async function login(page: Page, a: DemoAccount): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.tenant);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("navigation", { name: "Navigation principale" })).toBeVisible();
}

export async function open(page: Page, menu: string): Promise<void> {
  await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: menu, exact: true }).click();
}
