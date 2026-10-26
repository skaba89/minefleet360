import { defineConfig, devices } from "@playwright/test";

// E2E sur la pile locale (API + base de développement chargée par `minefleet seed-fictif`).
// Les identifiants fictifs sont lus dans le fichier désigné par MF_E2E_ACCOUNTS (sortie du seed) :
// jamais commités. Voir frontend/README.md.
// Les E2E créent des données et leurs traces contiennent des jetons : jamais contre la recette ou la production.
const apiUrl = process.env.MF_API_URL ?? "http://localhost:8000";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(apiUrl)) {
  throw new Error(`E2E refusés : MF_API_URL doit désigner une API locale (reçu ${apiUrl}).`);
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    locale: "fr-FR",
    timezoneId: "Africa/Conakry",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
