import { defineConfig, devices } from "@playwright/test";

// Parcours terrain hors ligne sur le build de production (service worker actif) servi par `vite preview`,
// qui relaie /api vers l'API locale. Mêmes garde-fous que les E2E : pile locale et comptes fictifs seulement.
const apiUrl = process.env.MF_API_URL ?? "http://localhost:8000";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(apiUrl)) {
  throw new Error(`E2E refusés : MF_API_URL doit désigner une API locale (reçu ${apiUrl}).`);
}

export default defineConfig({
  testDir: "./e2e-field",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:4173",
    locale: "fr-FR",
    timezoneId: "Africa/Conakry",
    trace: "retain-on-failure",
  },
  // L'émulation Android (Chrome mobile, écran tactile) ne remplace pas un essai sur appareil réel.
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "android", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run build && npx vite preview --host localhost --port 4173 --strictPort",
    url: "http://localhost:4173/connexion",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
