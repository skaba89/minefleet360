import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { TenantOnboardingPage } from "./TenantOnboardingPage";

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

const CHECKLIST = {
  steps: [
    {
      key: "subscription", label: "Essai ou abonnement actif",
      hint: "La plateforme active un essai ou un abonnement pour votre société.",
      count: 1, target: 1, done: true,
    },
    {
      key: "users", label: "Votre équipe est invitée",
      hint: "Au moins deux utilisateurs actifs (l'administrateur et un collègue).",
      count: 1, target: 2, done: false,
    },
    {
      key: "sites", label: "Vos sites sont créés",
      hint: "Créez au moins un site (mine, carrière, dépôt…).",
      count: 2, target: 1, done: true,
    },
    {
      key: "vehicles", label: "Votre flotte est enregistrée",
      hint: "Enregistrez au moins un véhicule actif.",
      count: 0, target: 1, done: false,
    },
    {
      key: "gps_trackers", label: "Vos véhicules sont équipés",
      hint: "Liez au moins un traceur GPS à un véhicule pour le suivi temps réel.",
      count: 0, target: 1, done: false,
    },
  ],
  done_count: 2, total: 5, progress_percent: 40,
};

it("affiche la progression réelle du démarrage", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue(CHECKLIST);
  mount(<TenantOnboardingPage />);
  expect(await screen.findByText(/2\/5 étapes réalisées \(40 %\)/)).toBeTruthy();
  expect(screen.getByText(/Essai ou abonnement actif/)).toBeTruthy();
  expect(screen.getByText(/1\/2\)/)).toBeTruthy();
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("40");
});

it("refuse l'accès sans la permission de lecture du tenant", () => {
  canMock.mockReturnValue(false);
  mount(<TenantOnboardingPage />);
  expect(screen.queryByText("Démarrage")).toBeNull();
  expect(getMock).not.toHaveBeenCalled();
});
