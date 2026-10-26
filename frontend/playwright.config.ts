import { defineConfig, devices } from "@playwright/test";

// E2E sur la pile locale (API + base de développement chargée par `minefleet seed-fictif`).
// Les identifiants fictifs sont lus dans le fichier désigné par MF_E2E_ACCOUNTS (sortie du seed) :
// jamais commités. Voir frontend/README.md.
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
