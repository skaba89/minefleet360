import { defineConfig, devices } from "@playwright/test";

// Parcours de démonstration : pile LOCALE chargée par `minefleet demo seed --profile qa`.
// Identifiants lus dans le fichier désigné par MF_DEMO_ACCOUNTS (sortie 600 du seed) : jamais commités.
// Lecture seule pour l'essentiel : les parcours vérifient que chaque écran affiche les données DEMO.
const apiUrl = process.env.MF_API_URL ?? "http://localhost:8000";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(apiUrl)) {
  throw new Error(`Parcours DEMO refusés : MF_API_URL doit désigner une API locale (reçu ${apiUrl}).`);
}

export default defineConfig({
  testDir: "./e2e-demo",
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
