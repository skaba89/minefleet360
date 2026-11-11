import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformCreateTenantPage, PlatformHealthPage, PlatformOverview, PlatformTenantsPage } from "./PlatformPages";

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

it("présente aux administrateurs plateforme les seules métadonnées des sociétés", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({
    page: 1, page_size: 20, total: 1,
    items: [{
      tenant_id: "11111111-1111-4111-8111-111111111111",
      code: "mine-a", display_name: "Mine A", status: "ACTIVE", is_demo: true,
      created_at: "2026-11-05T00:00:00Z", row_version: 1,
    }],
  });
  mount(<PlatformTenantsPage />);
  expect(await screen.findByText("Mine A")).toBeTruthy();
  expect(screen.getByText("Démonstration")).toBeTruthy();
  expect(screen.queryByText("Flotte GPS")).toBeNull();
  expect(getMock).toHaveBeenCalledWith("/platform/tenants", { page: 1, page_size: 20 });
});

it("n'appelle aucune API plateforme sans la permission correspondante", async () => {
  canMock.mockReturnValue(false);
  mount(<PlatformTenantsPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  await waitFor(() => expect(getMock).not.toHaveBeenCalled());
});

it("affiche le nombre de sociétés depuis l'API autorisée", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({ items: [], page: 1, page_size: 1, total: 7 });
  mount(<PlatformOverview />);
  expect((await screen.findByText("7")).closest("a")?.textContent).toContain("société(s) cliente(s)");
  expect(getMock).toHaveBeenCalledWith("/platform/tenants", { page: 1, page_size: 1 });
});

it("refuse la création d'une société sans permission et n'appelle pas l'API", () => {
  canMock.mockReturnValue(false);
  mount(<PlatformCreateTenantPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(requestMock).not.toHaveBeenCalled();
});

it("envoie une création de société via l'API protégée", async () => {
  canMock.mockReturnValue(true);
  requestMock.mockResolvedValue({ data: { tenant_id: "tenant-a" }, etag: null });
  mount(<PlatformCreateTenantPage />);
  fireEvent.change(screen.getByLabelText(/Code unique/), { target: { value: "mine-nord" } });
  fireEvent.change(screen.getByLabelText("Raison sociale"), { target: { value: "Mine du Nord SA" } });
  fireEvent.change(screen.getByLabelText("Nom affiché"), { target: { value: "Mine du Nord" } });
  fireEvent.change(screen.getByLabelText("E-mail du premier administrateur"), { target: { value: "admin@example.org" } });
  fireEvent.change(screen.getByLabelText("Nom du premier administrateur"), { target: { value: "Administrateur mine" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer et inviter" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith("/platform/tenants", {
    method: "POST",
    body: {
      code: "mine-nord", legal_name: "Mine du Nord SA", display_name: "Mine du Nord",
      default_timezone: "Africa/Conakry", admin_email: "admin@example.org",
      admin_display_name: "Administrateur mine",
    },
  }));
});

it("demande un motif et transmet If-Match pour suspendre une société", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({
    page: 1, page_size: 20, total: 1,
    items: [{
      tenant_id: "11111111-1111-4111-8111-111111111111", code: "mine-a",
      display_name: "Mine A", status: "ACTIVE", is_demo: true,
      created_at: "2026-11-05T00:00:00Z", row_version: 4,
    }],
  });
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformTenantsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Suspendre" }));
  fireEvent.change(screen.getByLabelText("Motif obligatoire"), { target: { value: "Suspension demandée après audit" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    "/platform/tenants/11111111-1111-4111-8111-111111111111/suspend",
    { method: "POST", body: { reason: "Suspension demandée après audit" }, ifMatch: '"4"' },
  ));
});

it("affiche les sondes de disponibilité quand elles répondent", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({ status: "ok" });
  mount(<PlatformHealthPage />);
  expect(await screen.findByText("API : Disponible")).toBeTruthy();
  expect(screen.getByText("Base et dépendances : Prêtes")).toBeTruthy();
  expect(getMock).toHaveBeenCalledWith("/health");
  expect(getMock).toHaveBeenCalledWith("/ready");
});

it("ne consulte pas les sondes depuis un compte non autorisé", () => {
  canMock.mockReturnValue(false);
  mount(<PlatformHealthPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(getMock).not.toHaveBeenCalled();
});
