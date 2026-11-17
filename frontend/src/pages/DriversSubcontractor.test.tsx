import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { call, read } from "../api/client";
import { DriversPage } from "./DriversPage";

/** Conducteur sous-traitant rattaché au référentiel (lot 1, tranche 2c) — saisie par HR, données fictives. */
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants: [{ role_code: "HR", scope_type: "TENANT", site_id: null }] }),
}));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({
    siteId: "s1",
    sites: [{ site_id: "s1", code: "MINE", name: "Mine fictive", status: "ACTIVE", timezone: "Africa/Conakry" }],
    timezoneOf: () => "Africa/Conakry",
  }),
}));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
}));
vi.mock("react-router", async (original) => ({
  ...(await original<typeof import("react-router")>()),
  useNavigate: () => vi.fn(),
}));

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) =>
    path === "/subcontractors"
      ? [{ subcontractor_id: "st-1", code: "ST-TRANS", legal_name: "Transports Fictifs SARL", status: "ACTIVE" }]
      : { items: [], total: 0, page: 1, page_size: 50 }) as never);
  vi.mocked(call).mockResolvedValue({ data: { driver_id: "d-1" }, etag: null } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("création d'un conducteur sous-traitant rattaché : entreprise pré-remplie, rattachement envoyé", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DriversPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Nouveau conducteur" }));
  expect(screen.queryByLabelText("Sous-traitant (référentiel)")).toBeNull(); // salarié par défaut
  fireEvent.change(screen.getByLabelText("Matricule (unique)"), { target: { value: "MAT-ST-1" } });
  fireEvent.change(screen.getByLabelText("Nom"), { target: { value: "Nom-Test" } });
  fireEvent.change(screen.getByLabelText("Prénom"), { target: { value: "Prénom" } });
  fireEvent.change(screen.getByLabelText("Contrat"), { target: { value: "SUBCONTRACTOR" } });
  await screen.findByRole("option", { name: "ST-TRANS — Transports Fictifs SARL" });
  fireEvent.change(screen.getByLabelText("Sous-traitant (référentiel)"), { target: { value: "st-1" } });
  expect((screen.getByLabelText("Entreprise sous-traitante") as HTMLInputElement).value).toBe("Transports Fictifs SARL");
  fireEvent.click(screen.getByRole("button", { name: "Créer le conducteur" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]![2]?.body).toMatchObject({
    employment_type: "SUBCONTRACTOR",
    external_company_name: "Transports Fictifs SARL",
    subcontractor_id: "st-1",
  });
  client.clear();
});
