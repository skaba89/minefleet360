import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformOverview, PlatformTenantsPage } from "./PlatformPages";

const { getMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
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
  expect(screen.getByRole("alert").textContent).toContain("Accès réservé");
  await waitFor(() => expect(getMock).not.toHaveBeenCalled());
});

it("affiche le nombre de sociétés depuis l'API autorisée", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({ items: [], page: 1, page_size: 1, total: 7 });
  mount(<PlatformOverview />);
  expect((await screen.findByText("7")).closest("a")?.textContent).toContain("société(s) cliente(s)");
  expect(getMock).toHaveBeenCalledWith("/platform/tenants", { page: 1, page_size: 1 });
});
