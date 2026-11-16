import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { call, read } from "../api/client";
import { SubcontractorsPage } from "./SubcontractorsPage";

let grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null as string | null }];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
}));

const active = {
  subcontractor_id: "st-1", code: "ST-TRANS", legal_name: "Transports Fictifs SARL", registration_number: "RCCM-1",
  tax_id: "NIF-1", country_code: "GN", status: "ACTIVE", status_reason: null, notes: null,
  created_at: "2026-11-16T08:00:00Z", updated_at: "2026-11-16T08:00:00Z", row_version: 3,
};
const suspended = { ...active, subcontractor_id: "st-2", code: "ST-SUSP", legal_name: "Engins Fictifs SA", status: "SUSPENDED", status_reason: "Assurance expirée" };

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SubcontractorsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockResolvedValue([active, suspended] as never);
  vi.mocked(call).mockResolvedValue({ data: active, etag: '"4"' } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
});

it("liste les sous-traitants avec leur statut et le motif de suspension", async () => {
  const client = show();
  expect(await screen.findByText("Transports Fictifs SARL")).toBeTruthy();
  expect(within(screen.getByRole("table")).getByText("Suspendue")).toBeTruthy();
  expect(screen.getByText("Assurance expirée")).toBeTruthy();
  client.clear();
});

it("création : code, raison sociale, identifiants légaux facultatifs, pays en majuscules", async () => {
  const client = show();
  fireEvent.click(await screen.findByRole("button", { name: "Nouveau sous-traitant" }));
  fireEvent.change(screen.getByLabelText("Code (unique)"), { target: { value: "ST-NEW" } });
  fireEvent.change(screen.getByLabelText("Raison sociale"), { target: { value: " Nouvelle Société " } });
  fireEvent.change(screen.getByLabelText("Pays (code ISO)"), { target: { value: "sn" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer le sous-traitant" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]).toEqual([
    "post",
    "/subcontractors",
    { body: { code: "ST-NEW", legal_name: "Nouvelle Société", registration_number: null, tax_id: null, country_code: "SN" } },
  ]);
  client.clear();
});

it("suspension : motif obligatoire, version envoyée en If-Match, seuls les champs modifiés partent", async () => {
  const client = show();
  fireEvent.click((await screen.findAllByRole("button", { name: "Modifier" }))[0]!);
  fireEvent.change(screen.getByLabelText("Statut"), { target: { value: "SUSPENDED" } });
  expect(screen.getByLabelText("Motif (obligatoire)")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Motif (obligatoire)"), { target: { value: "Assurance expirée" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]).toEqual([
    "patch",
    "/subcontractors/{subcontractor_id}",
    { path: { subcontractor_id: "st-1" }, body: { status: "SUSPENDED", status_reason: "Assurance expirée" }, ifMatch: '"3"' },
  ]);
  client.clear();
});

it("lecture seule : ni création ni modification pour la finance", async () => {
  grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }];
  const client = show();
  expect(await screen.findByText("Transports Fictifs SARL")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Nouveau sous-traitant" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Modifier" })).toBeNull();
  client.clear();
});

it("refuse l'accès sans la permission de lecture, sans appel serveur", () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  const client = show();
  expect(screen.getByText("Vous n'avez pas accès à cette page.")).toBeTruthy();
  expect(read).not.toHaveBeenCalled();
  client.clear();
});
