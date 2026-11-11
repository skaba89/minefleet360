import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { TenantSubscriptionPage } from "./TenantSubscriptionPage";

const { getMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
}));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ grants: [{ role_code: "TENANT_ADMIN", scope_type: "TENANT", site_id: null }] }),
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

it("affiche la formule, les échéances et les quotas de la société", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({
    subscription_id: "33333333-3333-4333-8333-333333333333",
    status: "ACTIVE",
    trial_ends_at: null,
    period_ends_at: "2027-01-15T00:00:00Z",
    plan: {
      plan_id: "22222222-2222-4222-8222-222222222222",
      code: "MINING_PRO", name: "Mining Pro", status: "ACTIVE",
      max_users: 100, max_sites: 20, max_vehicles: 200, max_gps_trackers: 250,
      document_retention_days: 1095, row_version: 1,
    },
  });
  mount(<TenantSubscriptionPage />);
  expect(await screen.findByText(/Mining Pro \(MINING_PRO\)/)).toBeTruthy();
  expect(screen.getByText("Actif")).toBeTruthy();
  expect(screen.queryAllByText("Illimité").length).toBe(0);
  expect(getMock).toHaveBeenCalledWith("/tenant/subscription");
});

it("refuse la page sans la permission de lecture", () => {
  canMock.mockReturnValue(false);
  mount(<TenantSubscriptionPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(getMock).not.toHaveBeenCalled();
});
