import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";

import { expect, type APIRequestContext, type Page } from "@playwright/test";

export interface Account {
  workspace: string;
  role: string;
  email: string;
  password: string;
}

/** Comptes fictifs lus dans la sortie de `minefleet seed-fictif` (lignes « espace RÔLE e-mail mot-de-passe »). */
export function accounts(): Account[] {
  const path = process.env.MF_E2E_ACCOUNTS;
  if (!path) throw new Error("MF_E2E_ACCOUNTS doit désigner le fichier de comptes fictifs (sortie du seed).");
  return readFileSync(path, "utf-8")
    .split(/\r?\n/)
    .map((line) => line.trim().split(/\s+/))
    .filter((parts) => parts.length === 4 && parts[2]!.includes("@"))
    .map(([workspace, role, email, password]) => ({ workspace: workspace!, role: role!, email: email!, password: password! }));
}

export function account(role: string, workspace?: string): Account {
  const found = accounts().find((a) => a.role === role && (!workspace || a.workspace === workspace));
  if (!found) throw new Error(`Compte fictif introuvable : ${role} ${workspace ?? ""}`);
  return found;
}

export async function apiLogin(request: APIRequestContext, a: Account): Promise<Record<string, string>> {
  const resp = await request.post("/api/v1/auth/login", {
    data: { workspace_code: a.workspace, email: a.email, password: a.password },
  });
  expect(resp.status()).toBe(200);
  return { Authorization: `Bearer ${(await resp.json()).access_token}` };
}

export async function uiLogin(page: Page, a: Account): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Code de l'espace de travail").fill(a.workspace);
  await page.getByLabel("Adresse e-mail").fill(a.email);
  await page.getByLabel("Mot de passe").fill(a.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: /^Bonjour/ })).toBeVisible();
}

/** Site du dispatcher : sa seule attribution de portée SITE. */
export async function dispatcherSite(request: APIRequestContext, headers: Record<string, string>): Promise<string> {
  const me = await (await request.get("/api/v1/me", { headers })).json();
  return me.grants.find((g: { scope_type: string }) => g.scope_type === "SITE").site_id;
}

/**
 * Prépare par l'API un couple véhicule ↔ conducteur éligible (ou non) sur le site donné.
 * Valeurs fictives uniques : aucune collision entre exécutions.
 */
export async function preparePair(
  request: APIRequestContext,
  workspace: string,
  siteId: string,
  { eligible }: { eligible: boolean },
): Promise<{ fleetNumber: string; driverLabel: string; driverOption: string }> {
  const admin = await apiLogin(request, account("TENANT_ADMIN", workspace));
  const hr = await apiLogin(request, account("HR", workspace));
  const suffix = Math.random().toString(36).slice(2, 8).toUpperCase();
  const categories = await (await request.get("/api/v1/vehicle-categories", { headers: admin })).json();
  const category = categories.find((c: { code: string }) => c.code === "RIGID_DUMP_TRUCK");
  const fleetNumber = `E2E-${suffix}`;
  const vehicle = await request.post("/api/v1/vehicles", {
    headers: admin,
    data: { site_id: siteId, vehicle_category_id: category.vehicle_category_id, fleet_number: fleetNumber },
  });
  expect(vehicle.status()).toBe(201);
  const lastName = `Nom-E2E-${suffix}`;
  const driver = await request.post("/api/v1/drivers", {
    headers: hr,
    data: { site_id: siteId, employee_number: `M-E2E-${suffix}`, last_name: lastName, first_name: "Test" },
  });
  expect(driver.status()).toBe(201);
  const driverId = (await driver.json()).driver_id;
  const license = await request.post(`/api/v1/drivers/${driverId}/licenses`, {
    headers: hr,
    data: {
      license_number: `PERMIS-FICTIF-E2E-${suffix}`,
      category_code: eligible ? "C" : "B",
      issue_date: "2020-01-01",
      expiry_date: "2035-01-01",
    },
  });
  expect(license.status()).toBe(201);
  const qualification = await request.post(`/api/v1/drivers/${driverId}/qualifications`, {
    headers: hr,
    data: {
      qualification_type: "DRIVING_AUTHORIZATION",
      vehicle_category_id: category.vehicle_category_id,
      valid_from: "2020-01-01",
    },
  });
  expect(qualification.status()).toBe(201);
  const driverLabel = `${lastName.toUpperCase()} Test`;
  return { fleetNumber, driverLabel, driverOption: `${driverLabel} — M-E2E-${suffix}` };
}

/** TOTP RFC 6238 (SHA1, 6 chiffres, 30 s) pour simuler l'application d'authentification du testeur. */
export function totpCode(base32Secret: string, offsetSeconds = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of base32Secret.replace(/[\s=]/g, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const step = Math.floor((Date.now() / 1000 + offsetSeconds) / 30);
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return value.toString().padStart(6, "0");
}
