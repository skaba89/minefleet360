import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformTenantSupportPage } from "./PlatformTenantSupportPage";

const { getMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
}));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ grants: [{ role_code: "PLATFORM_ADMIN", scope_type: "PLATFORM", site_id: null }] }),
}));
vi.mock("../lib/permissions", () => ({
  can: canMock,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mount(component: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const TENANT_ID = "88888888-8888-4888-8888-888888888888";
const TENANTS = {
  page: 1, page_size: 100, total: 1,
  items: [{
    tenant_id: TENANT_ID, code: "sima", display_name: "Sima Mines", status: "ACTIVE",
    is_demo: false, created_at: "2026-10-01T08:00:00Z", row_version: 3,
  }],
};
const OVERVIEW = {
  tenant: TENANTS.items[0],
  subscription: {
    subscription_id: "77777777-7777-4777-8777-777777777777",
    status: "TRIAL", effective_status: "EXPIRED",
    trial_ends_at: "2026-11-01T00:00:00Z", period_ends_at: null,
    plan: {
      plan_id: "66666666-6666-4666-8666-666666666666", code: "PARKO", name: "Parc 50",
      status: "ACTIVE", max_users: 10, max_sites: 5, max_vehicles: 50, max_gps_trackers: 50,
      document_retention_days: 365, price_monthly_gnf: 12_000_000, billing_period: "MONTHLY",
      row_version: 1,
    },
  },
  usage: [
    { field: "max_users", label: "Utilisateurs", usage: 4, limit: 10 },
    { field: "max_sites", label: "Sites", usage: 2, limit: 5 },
    { field: "max_vehicles", label: "Véhicules", usage: 18, limit: 50 },
    { field: "max_gps_trackers", label: "Traceurs GPS", usage: 6, limit: 50 },
  ],
  users: { active: 4, invited: 1, disabled: 2 },
  invoices: [{
    invoice_id: "55555555-5555-4555-8555-555555555555", number: "MF-2026-00012",
    status: "ISSUED", total_gnf: 14_160_000, created_at: "2026-11-05T09:00:00Z",
  }],
};

it("affiche la vue consolidée du compte sélectionné", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(OVERVIEW),
  );
  mount(<PlatformTenantSupportPage />);
  await screen.findByRole("option", { name: /Sima Mines/ });
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  expect(await screen.findByText(/Parc 50 — Essai expiré/)).toBeTruthy();
  expect(screen.getByText(/statut enregistré : Essai\)/)).toBeTruthy();
  expect(screen.getByText("Usage face aux limites du plan")).toBeTruthy();
  expect(screen.getByText("18")).toBeTruthy(); // usage véhicules
  expect(screen.getByText("6")).toBeTruthy(); // usage traceurs GPS
  expect(screen.getByText("4 actifs, 1 en attente, 2 désactivés")).toBeTruthy();
  expect(screen.getByText("MF-2026-00012")).toBeTruthy();
  expect(screen.getByText("14 160 000 GNF")).toBeTruthy();
});

it("refuse l'accès à un non-opérateur plateforme", () => {
  canMock.mockReturnValue(false);
  mount(<PlatformTenantSupportPage />);
  expect(screen.queryByText("Support société")).toBeNull();
  expect(getMock).not.toHaveBeenCalled();
});
