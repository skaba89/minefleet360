import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { read } from "../api/client";
import { ContractRevenueSection } from "./ContractRevenue";

vi.mock("../site/SiteContext", () => ({
  useSites: () => ({ siteId: null, sites: [{ site_id: "s1", code: "MINE", name: "Mine fictive" }], timezoneOf: () => "Africa/Conakry" }),
}));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn() }));

const report = {
  period_start: "2026-10-18T00:00:00Z",
  period_end: "2026-11-17T00:00:00Z",
  contracts: [
    { contract_id: "c1", contract_reference: "CT-001", site_id: "s1", amount: "850000.00", currency: "GNF", status: "PARTIAL", tonnes: "34.000", missions_completed: 2, missing: ["pesée dégradée en attente d'approbation (exclue)"] },
    { contract_id: "c2", contract_reference: "CT-002", site_id: "s1", amount: null, currency: null, status: "INSUFFICIENT", tonnes: "0.000", missions_completed: 1, missing: ["tarif HOUR : quantité non mesurée par mission"] },
  ],
  sites: [
    { site_id: "s1", revenue: null, revenue_status: "INSUFFICIENT", cost: "300000.00", cost_status: "COMPLETE", currency: "GNF", margin: null, margin_percent: null, missions_without_contract: 0, not_comparable_reason: "revenu indisponible (tarif manquant, quantité non mesurée ou devises multiples)" },
  ],
};

beforeEach(() => vi.mocked(read).mockResolvedValue(report as never));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("affiche les revenus mesurés, les manques et l'absence de marge inventée", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><ContractRevenueSection days="30" /></QueryClientProvider>);
  const byContract = await screen.findByRole("table", { name: "Revenus par contrat" });
  expect(within(byContract).getByText(/850\s000 GNF/)).toBeTruthy();
  expect(within(byContract).getByText("Partiel (minimum)")).toBeTruthy();
  expect(within(byContract).getByText("tarif HOUR : quantité non mesurée par mission")).toBeTruthy();
  const bySite = screen.getByRole("table", { name: "Marge par site" });
  expect(within(bySite).getByText(/revenu indisponible/)).toBeTruthy();
  expect(within(bySite).queryByText(/%\)/)).toBeNull();
  client.clear();
});
