import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { read } from "../api/client";
import { TodoPanel } from "./TodoPanel";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: null }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn() }));

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><TodoPanel /></MemoryRouter></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string, options?: { query?: Record<string, unknown> }) => {
    if (path === "/hse/summary") return { overdue_actions: 2 };
    if (path === "/hse/corrective-actions") return { total: 1 };
    if (path === "/hse/incidents") return { total: 0 };
    if (path === "/work-orders") return { total: options?.query?.status === "REQUESTED" ? 3 : 0 };
    if (path === "/tyres") return { total: 4 };
    return { total: 0 };
  }) as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("le HSE voit ses actions et les retards, sans interroger ce qu'il ne peut pas lire", async () => {
  grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null }];
  const client = show();
  expect(await screen.findByText("2 action(s) corrective(s) HSE en retard")).toBeTruthy();
  expect(screen.getByText("1 action(s) corrective(s) HSE à réaliser par vous")).toBeTruthy();
  expect(screen.queryByText(/incident\(s\) critique/)).toBeNull(); // compteur nul masqué
  const paths = vi.mocked(read).mock.calls.map((c) => c[0]);
  expect(paths).not.toContain("/tyres");
  expect(paths).not.toContain("/fuel/alerts");
  client.clear();
});

it("le chef d'atelier voit les demandes à valider et les pneus en alerte", async () => {
  grants = [{ role_code: "WORKSHOP_CHIEF", scope_type: "TENANT", site_id: null }];
  const client = show();
  expect(await screen.findByText("3 demande(s) d'intervention à valider")).toBeTruthy();
  expect(screen.getByText("4 pneu(s) en alerte (usure, pression ou contrôle en retard)")).toBeTruthy();
  client.clear();
});

it("sans aucun indicateur accessible, le panneau n'apparaît pas", () => {
  grants = [{ role_code: "HR", scope_type: "TENANT", site_id: null }];
  const client = show();
  expect(screen.queryByRole("region", { name: "À traiter" })).toBeNull();
  expect(read).not.toHaveBeenCalled();
  client.clear();
});
