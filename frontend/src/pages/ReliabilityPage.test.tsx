import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { read } from "../api/client";
import { ReliabilityPage } from "./ReliabilityPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "WORKSHOP_CHIEF", scope_type: "TENANT", site_id: null },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({ siteId: null, sites: [{ site_id: "s1", code: "MINE" }], timezoneOf: () => "Africa/Conakry" }),
}));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn() }));

const report = {
  period_start: "2026-08-04T00:00:00Z",
  period_end: "2026-11-02T00:00:00Z",
  period_hours: "2160.00",
  currency: "GNF",
  totals: {
    vehicles: 2, failures: 3, downtime_hours: "216.00", availability_percent: "95.00", mttr_hours: "12.50",
    mtbf_hours: "1368.00", labour_hours: "6.00", parts_cost_known: "1500000", parts_cost_complete: false,
  },
  vehicles: [
    {
      vehicle_id: "v1", fleet_number: "CAM-FICTIF-1", site_id: "s1", vehicle_status: "AVAILABLE", failures: 3,
      closed_corrective: 2, open_work_orders: 1, downtime_hours: "216.00", availability_percent: "90.00",
      mttr_hours: "12.50", mtbf_hours: "648.00", labour_hours: "6.00", parts_cost_known: "1500000",
      parts_cost_complete: false,
    },
  ],
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><ReliabilityPage /></MemoryRouter></QueryClientProvider>);
  return client;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "WORKSHOP_CHIEF", scope_type: "TENANT", site_id: null }];
});

it("affiche les indicateurs et signale un coût pièces incomplet", async () => {
  vi.mocked(read).mockResolvedValue(report as never);
  const client = show();
  expect(await screen.findByText("CAM-FICTIF-1")).toBeTruthy();
  expect(screen.getByText("90 %")).toBeTruthy();
  expect(screen.getAllByText(/≥ 1\s500\s000 GNF/).length).toBe(2);
  expect(screen.getByText(/1 OT ouvert/)).toBeTruthy();
  expect(read).toHaveBeenCalledWith("/maintenance/reliability", expect.objectContaining({ query: expect.objectContaining({ site_id: null }) }));
  client.clear();
});

it("ne charge rien sans la permission", () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  const client = show();
  expect(screen.getByText("Vous n'avez pas accès à cette page.")).toBeTruthy();
  expect(read).not.toHaveBeenCalled();
  client.clear();
});
