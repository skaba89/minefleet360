import { defineConfig, devices } from "@playwright/test";

// Vérification navigateur publique et isolée : aucun compte, API ni donnée métier.
export default defineConfig({
  testDir: "./e2e-smoke",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    locale: "fr-FR",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173/connexion",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
