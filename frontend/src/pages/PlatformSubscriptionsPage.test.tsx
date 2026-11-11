import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformSubscriptionsPage } from "./PlatformSubscriptionsPage";

const { getMock, requestMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  requestMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
  request: requestMock,
}));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ grants: [{ role_code: "PLATFORM_ADMIN", scope_type: "TENANT", site_id: null }] }),
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

const TENANT_ID = "11111111-1111-4111-8111-111111111111";
const PLAN_ID = "22222222-2222-4222-8222-222222222222";
const SUB_ID = "33333333-3333-4333-8333-333333333333";

const TENANTS = { items: [{ tenant_id: TENANT_ID, code: "mine-a", display_name: "Mine A", status: "ACTIVE", is_demo: true, created_at: "2026-11-05T00:00:00Z", row_version: 1 }] };
const SUBS = {
  page: 1, page_size: 20, total: 1,
  items: [{
    subscription_id: SUB_ID, tenant_id: TENANT_ID, plan_id: PLAN_ID,
    plan_code: "BUSINESS", plan_name: "Business", status: "TRIAL",
    trial_ends_at: "2026-12-01T00:00:00Z", period_ends_at: null,
    suspended_at: null, cancelled_at: null, suspension_reason: null, row_version: 1,
  }],
};

it("affiche l'historique d'abonnement d'une société sélectionnée", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(SUBS),
  );
  mount(<PlatformSubscriptionsPage />);
  await screen.findByRole("option", { name: /mine-a/ }); // attendre le chargement des options
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  expect(await screen.findByText(/BUSINESS/)).toBeTruthy();
  expect(screen.getByText("Essai")).toBeTruthy();
  await waitFor(() =>
    expect(getMock).toHaveBeenCalledWith(`/platform/tenants/${TENANT_ID}/subscriptions`, { page: 1, page_size: 20 }),
  );
});

it("propose les actions du cycle de vie selon le statut", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(SUBS),
  );
  mount(<PlatformSubscriptionsPage />);
  await screen.findByRole("option", { name: /mine-a/ }); // attendre le chargement des options
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  await screen.findByText(/BUSINESS/);
  expect(screen.getByRole("button", { name: "Activer" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Suspendre" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Annuler" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Réactiver" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Renouveler" })).toBeNull();
});

it("suspend avec motif et If-Match", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(SUBS),
  );
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformSubscriptionsPage />);
  await screen.findByRole("option", { name: /mine-a/ }); // attendre le chargement des options
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  fireEvent.click(await screen.findByRole("button", { name: "Suspendre" }));
  fireEvent.change(screen.getByLabelText("Motif obligatoire"), { target: { value: "Impayé constaté" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    `/platform/tenants/${TENANT_ID}/subscriptions/${SUB_ID}/suspend`,
    { method: "POST", body: { reason: "Impayé constaté" }, ifMatch: '"1"' },
  ));
});

it("souscrit un essai en convertissant la durée", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) => {
    if (path === "/platform/tenants") return Promise.resolve(TENANTS);
    if (path === "/platform/saas-plans") {
      return Promise.resolve({
        items: [{ plan_id: PLAN_ID, code: "BUSINESS", name: "Business", status: "ACTIVE", max_users: 25, max_sites: 5, max_vehicles: 40, max_gps_trackers: 40, document_retention_days: 365, row_version: 1 }],
      });
    }
    return Promise.resolve(SUBS);
  });
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformSubscriptionsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Souscrire un abonnement" }));
  // Deux selects listent les sociétés (page + formulaire) : attendre celui du formulaire.
  await screen.findAllByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société cliente"), { target: { value: TENANT_ID } });
  fireEvent.change(screen.getByLabelText("Plan (actifs uniquement)"), { target: { value: PLAN_ID } });
  fireEvent.click(screen.getByRole("button", { name: "Souscrire" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    `/platform/tenants/${TENANT_ID}/subscriptions`,
    { method: "POST", body: { plan_id: PLAN_ID, trial_days: 30, notes: null } },
  ));
});

it("refuse la page sans la permission de gestion", () => {
  canMock.mockReturnValue(false);
  mount(<PlatformSubscriptionsPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(getMock).not.toHaveBeenCalled();
});
