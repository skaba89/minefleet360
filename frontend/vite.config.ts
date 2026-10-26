/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En développement, l'API est servie sous la même origine via le proxy : le cookie de rafraîchissement
// (httpOnly, SameSite=Strict, chemin /api/v1/auth) fonctionne sans CORS (ADR-003).
const apiTarget = process.env.MF_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
