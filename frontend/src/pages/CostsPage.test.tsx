import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { read } from "../api/client";
import { CostsPage } from "./CostsPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: null, sites: [{ site_id: "s1", code: "MINE", name: "Mine" }] }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const zero = { amount: "0", status: "COMPLETE", currency: null, missing: [] };
const report = {
  period_start: "2026-10-03T00:00:00Z",
  period_end: "2026-11-02T00:00:00Z",
  vehicles: [
    {
      vehicle_id: "v1", fleet_number: "CAM-COUTEUX", site_id: "s1",
      fuel: { amount: "1200000.00", status: "ESTIMATED", currency: "GNF", missing: [] },
      parts: { amount: "300000.00", status: "COMPLETE", currency: "GNF", missing: [] },
      labour: { amount: "100000.00", status: "COMPLETE", currency: "GNF", missing: [] },
      tyres: zero, total: "1600000.00", total_status: "ESTIMATED", currency: "GNF", missing: [],
      km: "500.0", hours: "0", tonnes: "0.000", missions: 0, cost_per_km: "3200.00", cost_per_hour: null,
      cost_per_tonne: null, cost_per_mission: null,
    },
    {
      vehicle_id: "v2", fleet_number: "PELLE-SANS-TAUX", site_id: "s1", fuel: zero, parts: zero,
      labour: { amount: null, status: "INSUFFICIENT", currency: null, missing: ["taux horaire de main-d'œuvre"] },
      tyres: zero, total: null, total_status: "INSUFFICIENT", currency: null, missing: ["taux horaire de main-d'œuvre"],
      km: "0", hours: "0", tonnes: "0.000", missions: 0, cost_per_km: null, cost_per_hour: null, cost_per_tonne: null,
      cost_per_mission: null,
    },
  ],
  sites: [{ site_id: "s1", total: "1600000.00", total_status: "PARTIAL", vehicles: 2 }],
};

beforeEach(() => {
  vi.mocked(read).mockResolvedValue(report as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
});

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><CostsPage /></MemoryRouter></QueryClientProvider>);
  return client;
}

it("distingue coûts estimés, complets et données insuffisantes, sans chiffre inventé", async () => {
  const client = show();
  expect(await screen.findByText("CAM-COUTEUX")).toBeTruthy();
  expect(screen.getAllByText("Estimé").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/1\s600\s000 GNF/).length).toBeGreaterThan(0);
  expect(screen.getByText(/^\/ km : 3\s200\sGNF$/)).toBeTruthy();
  expect(screen.getAllByText("Données insuffisantes").length).toBeGreaterThan(0);
  expect(screen.getByText(/Manque : taux horaire de main-d'œuvre/)).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Taux horaires de main-d'œuvre" })).toBeNull();
  client.clear();
});

it("la finance gère les taux horaires", async () => {
  grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }];
  vi.mocked(read).mockImplementation((async (path: string) => (path === "/costs/labour-rates" ? [] : report)) as never);
  const client = show();
  expect(await screen.findByRole("region", { name: "Taux horaires de main-d'œuvre" })).toBeTruthy();
  client.clear();
});
