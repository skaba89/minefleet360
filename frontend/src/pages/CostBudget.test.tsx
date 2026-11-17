import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { call, read } from "../api/client";
import { CostBudgetSection } from "./CostBudget";

let grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null as string | null }];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({ siteId: null, sites: [{ site_id: "s1", code: "MINE", name: "Mine fictive" }], timezoneOf: () => "Africa/Conakry" }),
}));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const base = { site_id: "s1", month: "2026-11", actual_currency: "GNF", budget_currency: "GNF" };
const report = {
  from_month: "2026-06",
  to_month: "2026-11",
  rows: [
    { ...base, component: "FUEL", budget_amount: "1000000.00", actual_amount: "1200000.00", actual_status: "ESTIMATED", variance_amount: "200000.00", variance_percent: "20.00", not_comparable_reason: null },
    { ...base, component: "LABOUR", budget_amount: "40.00", budget_currency: "USD", actual_amount: "100000.00", actual_status: "COMPLETE", variance_amount: null, variance_percent: null, not_comparable_reason: "devises différentes : aucune conversion" },
    { ...base, component: "TYRES", budget_amount: null, budget_currency: null, actual_amount: "0.00", actual_status: "COMPLETE", variance_amount: null, variance_percent: null, not_comparable_reason: "aucun budget saisi" },
  ],
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><CostBudgetSection /></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockResolvedValue(report as never);
  vi.mocked(call).mockResolvedValue({ data: {}, etag: null } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }];
});

it("affiche l'écart en dépassement, et le motif quand la comparaison est impossible", async () => {
  const client = show();
  const table = await screen.findByRole("table");
  expect(within(table).getByText(/\+200\s000 GNF \(\+20\.00 %\)/)).toBeTruthy();
  expect(within(table).getByText("devises différentes : aucune conversion")).toBeTruthy();
  expect(within(table).getByText("Estimé")).toBeTruthy();
  expect(within(table).queryByText("Pneumatiques")).toBeNull(); // ni budget ni coût : ligne masquée
  client.clear();
});

it("saisie d'un budget par la finance : site, mois, composante, montant, devise en majuscules", async () => {
  const client = show();
  fireEvent.click(await screen.findByRole("button", { name: "Saisir un budget" }));
  fireEvent.change(screen.getByLabelText("Site"), { target: { value: "s1" } });
  fireEvent.change(screen.getByLabelText("Mois"), { target: { value: "2026-12" } });
  fireEvent.change(screen.getByLabelText("Composante"), { target: { value: "PARTS" } });
  fireEvent.change(screen.getByLabelText("Montant"), { target: { value: "300000" } });
  fireEvent.change(screen.getByLabelText("Devise (ISO)"), { target: { value: "gnf" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer le budget" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]).toEqual([
    "post",
    "/costs/budgets",
    { body: { site_id: "s1", month: "2026-12", component: "PARTS", amount: "300000", currency: "GNF", note: null } },
  ]);
  client.clear();
});

it("lecture seule sans la permission de gestion du budget", async () => {
  grants = [{ role_code: "AUDITOR", scope_type: "TENANT", site_id: null }];
  const client = show();
  await screen.findByRole("table");
  expect(screen.queryByRole("button", { name: "Saisir un budget" })).toBeNull();
  client.clear();
});
