import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionsPage } from "./SessionsPage";

const sessionCourante = {
  auth_session_id: "11111111-1111-1111-1111-111111111111",
  ip_address: "10.0.0.8",
  user_agent: "Mozilla/5.0 Chrome/126.0",
  amr: ["pwd"],
  created_at: "2026-11-09T07:00:00Z",
  last_seen_at: "2026-11-09T08:00:00Z",
  expires_at: "2026-11-09T19:00:00Z",
  is_current: true,
};

const autreSession = {
  ...sessionCourante,
  auth_session_id: "22222222-2222-2222-2222-222222222222",
  ip_address: "41.79.22.4",
  user_agent: "Mozilla/5.0 Firefox/128.0",
  is_current: false,
};

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  read: vi.fn(async (path: string) => {
    if (path === "/me/sessions") return [sessionCourante, autreSession];
    throw new Error(`chemin inattendu : ${path}`);
  }),
  call: vi.fn(async (method: string, template: string) => {
    if (method === "post" && template === "/me/sessions/revoke-others") return { data: { revoked: 1 } };
    if (method === "post" && template === "/me/sessions/{session_id}/revoke") return { data: undefined };
    throw new Error(`appel inattendu : ${method} ${template}`);
  }),
}));

vi.mock("../auth/AuthContext", async (original) => ({
  ...await original<typeof import("../auth/AuthContext")>(),
  useMe: () => ({
    user_account_id: "u1",
    display_name: "Test",
    email: "t@example.com",
    workspace_code: "ws",
    tenant_display_name: "WS",
    timezone: "Africa/Conakry",
    grants: [],
    mfa_enabled: false,
    mfa_enrollment_required: false,
    is_demo: false,
  }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SessionsPage />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(cleanup);

describe("écran Mes sessions", () => {
  it("affiche les sessions actives avec la session courante marquée", async () => {
    renderPage();
    expect(await screen.findByText(/Chrome/)).toBeTruthy();
    expect(screen.getByText(/Firefox/)).toBeTruthy();
    expect(screen.getByText("(session courante)")).toBeTruthy();
    expect(screen.getByText("10.0.0.8")).toBeTruthy();
    expect(screen.getByText("41.79.22.4")).toBeTruthy();
  });

  it("propose de fermer les autres sessions dès qu'il y en a plus d'une", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole("button", { name: "Fermer toutes les autres sessions" })).toBeTruthy());
    expect(screen.getAllByRole("button", { name: "Fermer" }).length).toBe(2);
  });

  it("traduit la fermeture groupée en message clair", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole("button", { name: "Fermer toutes les autres sessions" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Fermer toutes les autres sessions" }));
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("1 autre(s) session(s) fermée(s)");
  });
});
