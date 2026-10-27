import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);

describe("connexion", () => {
  it("sans session, redirige vers le formulaire et affiche l'erreur française du serveur", async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return json(401, { code: "AUTH_REQUIRED", message_fr: "Authentification requise.", details: null, request_id: null });
      return json(401, {
        code: "INVALID_CREDENTIALS",
        message_fr: "Identifiants invalides.",
        details: null,
        request_id: "req-1",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    expect(await screen.findByRole("heading", { name: "MINEFLEET 360" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Code de l'espace de travail"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret-fictif" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Identifiants invalides.");
    expect((screen.getByLabelText("Mot de passe") as HTMLInputElement).value).toBe("");
    const loginCall = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/auth/login"));
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      workspace_code: "demo",
      email: "a@example.com",
      password: "secret-fictif",
    });
  });

  it("restaure la session par le cookie et affiche l'accueil", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/refresh"))
          return json(200, { access_token: "jeton", token_type: "bearer", expires_in: 900, user: {} });
        if (url.endsWith("/me"))
          return json(200, {
            user_account_id: "u",
            display_name: "Awa Fictive",
            email: "awa@example.com",
            workspace_code: "demo",
            tenant_display_name: "Société fictive",
            timezone: "Africa/Conakry",
            grants: [{ role_code: "HR", scope_type: "TENANT", site_id: null }],
          });
        if (url.includes("/sites")) return json(200, { items: [], page: 1, page_size: 200, total: 0 });
        return json(404, { code: "NOT_FOUND", message_fr: "Ressource introuvable.", details: null, request_id: null });
      }),
    );
    renderApp();
    expect(await screen.findByRole("heading", { name: "Bonjour Awa Fictive" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Véhicules" })).toBeNull(); // RH ne lit pas le parc
    expect(screen.getAllByRole("link", { name: /Affectations/ }).length).toBeGreaterThan(0);
  });
});

describe("déconnexion", () => {
  it("ne simule pas la déconnexion si le serveur est injoignable (SEC1C-R-08)", async () => {
    let offline = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (offline) throw new TypeError("Failed to fetch");
        if (url.endsWith("/auth/refresh"))
          return json(200, { access_token: "jeton", token_type: "bearer", expires_in: 900, user: {} });
        if (url.endsWith("/me"))
          return json(200, {
            user_account_id: "u",
            display_name: "Awa Fictive",
            email: "awa@example.com",
            workspace_code: "demo",
            tenant_display_name: "Société fictive",
            timezone: "Africa/Conakry",
            grants: [],
          });
        return json(200, { items: [], page: 1, page_size: 200, total: 0 });
      }),
    );
    renderApp();
    await screen.findByRole("heading", { name: "Bonjour Awa Fictive" });
    offline = true;
    fireEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Déconnexion non confirmée");
    expect(screen.getByRole("heading", { name: "Bonjour Awa Fictive" })).toBeTruthy();
  });
});

describe("double authentification", () => {
  it("demande le code après le mot de passe puis ouvre la session", async () => {
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url.endsWith("/auth/refresh"))
        return json(401, { code: "AUTH_REQUIRED", message_fr: "Authentification requise.", details: null, request_id: null });
      if (url.endsWith("/auth/login")) return json(200, { mfa_required: true, mfa_token: "defi-fictif-123", expires_in: 300 });
      if (url.endsWith("/auth/mfa/verify"))
        return json(200, { access_token: "jeton", token_type: "bearer", expires_in: 900, user: {} });
      if (url.endsWith("/me"))
        return json(200, {
          user_account_id: "u",
          display_name: "Awa Fictive",
          email: "awa@example.com",
          workspace_code: "demo",
          tenant_display_name: "Société fictive",
          timezone: "Africa/Conakry",
          grants: [],
          mfa_enabled: true,
          mfa_enrollment_required: false,
        });
      return json(200, { items: [], page: 1, page_size: 200, total: 0 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await screen.findByRole("heading", { name: "MINEFLEET 360" });
    fireEvent.change(screen.getByLabelText("Code de l'espace de travail"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Adresse e-mail"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "secret-fictif" } });
    fireEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    fireEvent.change(await screen.findByLabelText("Code de vérification"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Valider le code" }));
    expect(await screen.findByRole("heading", { name: "Bonjour Awa Fictive" })).toBeTruthy();
    const verify = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/auth/mfa/verify"));
    expect(JSON.parse(String(verify?.[1]?.body))).toEqual({ mfa_token: "defi-fictif-123", code: "123456" });
  });

  it("enrôlement exigé : seule la page Sécurité est proposée", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/auth/refresh"))
          return json(200, { access_token: "jeton", token_type: "bearer", expires_in: 900, user: {} });
        if (url.endsWith("/me/mfa"))
          return json(200, { enabled: false, required: true, enabled_at: null, recovery_codes_remaining: 0 });
        if (url.endsWith("/me"))
          return json(200, {
            user_account_id: "u",
            display_name: "Admin Fictif",
            email: "admin@example.com",
            workspace_code: "demo",
            tenant_display_name: "Société fictive",
            timezone: "Africa/Conakry",
            grants: [{ role_code: "TENANT_ADMIN", scope_type: "TENANT", site_id: null }],
            mfa_enabled: false,
            mfa_enrollment_required: true,
          });
        return json(200, { items: [], page: 1, page_size: 200, total: 0 });
      }),
    );
    renderApp();
    expect((await screen.findByRole("alert")).textContent).toContain("Votre rôle exige la double authentification");
    expect(screen.queryByRole("navigation", { name: "Navigation principale" })).toBeNull();
    expect(await screen.findByRole("button", { name: "Commencer" })).toBeTruthy();
  });
});
