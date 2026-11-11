import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformPlansPage } from "./PlatformPlansPage";

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

const PLAN_PAGE = {
  page: 1, page_size: 20, total: 2,
  items: [
    {
      plan_id: "22222222-2222-4222-8222-222222222222",
      code: "STARTER", name: "Starter", status: "ACTIVE",
      max_users: 5, max_sites: 1, max_vehicles: 5, max_gps_trackers: 5,
      document_retention_days: 90, row_version: 1,
    },
    {
      plan_id: "33333333-3333-4333-8333-333333333333",
      code: "ENTERPRISE", name: "Enterprise", status: "RETIRED",
      max_users: null, max_sites: null, max_vehicles: null, max_gps_trackers: null,
      document_retention_days: null, row_version: 3,
    },
  ],
};

it("affiche le catalogue de plans avec quotas et illimités", async () => {
  canMock.mockImplementation((_grants: unknown, permission: string) => permission === "billing.plan.list");
  getMock.mockResolvedValue(PLAN_PAGE);
  mount(<PlatformPlansPage />);
  expect(await screen.findByText("STARTER")).toBeTruthy();
  expect(screen.getByText("ENTERPRISE")).toBeTruthy();
  expect(screen.getAllByText("Illimité").length).toBeGreaterThanOrEqual(5);
  expect(screen.getByText("Retiré")).toBeTruthy();
  expect(getMock).toHaveBeenCalledWith("/platform/saas-plans", { page: 1, page_size: 20 });
});

it("masque la gestion et la création sans les permissions correspondantes", async () => {
  canMock.mockImplementation((_grants: unknown, permission: string) => permission === "billing.plan.list");
  getMock.mockResolvedValue(PLAN_PAGE);
  mount(<PlatformPlansPage />);
  await screen.findByText("STARTER");
  expect(screen.queryByRole("button", { name: "Créer un plan" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Modifier" })).toBeNull();
  expect(requestMock).not.toHaveBeenCalled();
});

it("refuse la page sans la permission de lecture", async () => {
  canMock.mockReturnValue(false);
  mount(<PlatformPlansPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  await waitFor(() => expect(getMock).not.toHaveBeenCalled());
});

it("crée un plan avec quotas convertis (vide = null)", async () => {
  canMock.mockImplementation(
    (_grants: unknown, permission: string) => permission === "billing.plan.list" || permission === "billing.plan.create",
  );
  getMock.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 });
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformPlansPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Créer un plan" }));
  fireEvent.change(screen.getByLabelText(/Code \(majuscules/), { target: { value: "BUSINESS_TEST" } });
  fireEvent.change(screen.getByLabelText("Nom affiché"), { target: { value: "Business Test" } });
  fireEvent.change(screen.getByLabelText(/Quota utilisateurs/), { target: { value: "25" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith("/platform/saas-plans", {
    method: "POST",
    body: {
      code: "BUSINESS_TEST", name: "Business Test", description: null, status: "DRAFT",
      max_users: 25, max_sites: null, max_vehicles: null, max_gps_trackers: null,
      document_retention_days: null,
    },
  }));
});

it("modifie un plan en transmettant If-Match et retire un quota", async () => {
  canMock.mockImplementation(
    (_grants: unknown, permission: string) => permission === "billing.plan.list" || permission === "billing.plan.update",
  );
  getMock.mockResolvedValue(PLAN_PAGE);
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformPlansPage />);
  const modifierButtons = await screen.findAllByRole("button", { name: "Modifier" });
  fireEvent.click(modifierButtons[0]!); // plan STARTER
  fireEvent.change(screen.getByLabelText(/Quota traceurs GPS/), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    "/platform/saas-plans/22222222-2222-4222-8222-222222222222",
    {
      method: "PATCH",
      body: {
        name: "Starter", status: "ACTIVE", max_users: 5, max_sites: 1, max_vehicles: 5,
        max_gps_trackers: null, document_retention_days: 90,
      },
      ifMatch: '"1"',
    },
  ));
});

it("désactive la modification d'un plan retiré (état terminal)", async () => {
  canMock.mockImplementation(
    (_grants: unknown, permission: string) => permission === "billing.plan.list" || permission === "billing.plan.update",
  );
  getMock.mockResolvedValue(PLAN_PAGE);
  mount(<PlatformPlansPage />);
  const buttons = await screen.findAllByRole("button", { name: "Modifier" }) as HTMLButtonElement[];
  expect(buttons[1]?.disabled).toBe(true); // plan ENTERPRISE
  expect(requestMock).not.toHaveBeenCalled();
});
