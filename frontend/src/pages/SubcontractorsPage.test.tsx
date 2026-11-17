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

const performance = {
  period_start: "2026-08-18T00:00:00Z",
  period_end: "2026-11-16T00:00:00Z",
  tonnage_visible: false,
  subcontractors: [
    {
      subcontractor_id: "st-1", code: "ST-TRANS", legal_name: "Transports Fictifs SARL", status: "ACTIVE",
      availability_target_percent: "90.00", vehicles: 2, service_hours: "200.00", downtime_hours: "20.00",
      availability_percent: "90.00", sla_met: true, failures: 1, mtbf_hours: "180.00", mttr_hours: "20.00",
      operating_hours: null, measured_tonnes: null, tonnes_per_operating_hour: null, tonnage_pending: false,
    },
    {
      subcontractor_id: "st-2", code: "ST-SUSP", legal_name: "Engins Fictifs SA", status: "SUSPENDED",
      availability_target_percent: "95.00", vehicles: 1, service_hours: "100.00", downtime_hours: "10.00",
      availability_percent: "90.00", sla_met: false, failures: 1, mtbf_hours: "90.00", mttr_hours: "10.00",
      operating_hours: null, measured_tonnes: null, tonnes_per_operating_hour: null, tonnage_pending: false,
    },
  ],
};

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) =>
    path === "/subcontractors/performance" ? performance : [active, suspended]) as never);
  vi.mocked(call).mockResolvedValue({ data: active, etag: '"4"' } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
});

it("liste les sous-traitants avec leur statut et le motif de suspension", async () => {
  const client = show();
  await screen.findAllByText("Transports Fictifs SARL");
  const list = screen.getAllByRole("table")[0]!; // le référentiel ; la performance suit dans sa propre section
  expect(within(list).getByText("Transports Fictifs SARL")).toBeTruthy();
  expect(within(list).getByText("Suspendue")).toBeTruthy();
  expect(within(list).getByText("Assurance expirée")).toBeTruthy();
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
    {
      body: {
        code: "ST-NEW",
        legal_name: "Nouvelle Société",
        registration_number: null,
        tax_id: null,
        country_code: "SN",
        availability_target_percent: null,
      },
    },
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
  expect((await screen.findAllByText("Transports Fictifs SARL")).length).toBeGreaterThan(0);
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

it("performance : disponibilité mesurée comparée à l'objectif SLA, sans productivité si le tonnage est masqué", async () => {
  const client = show();
  const section = await screen.findByRole("region", { name: "Performance des sous-traitants" });
  expect(await within(section).findByText("Atteint")).toBeTruthy();
  expect(within(section).getByText("Non atteint")).toBeTruthy();
  expect(within(section).getByText("180 h")).toBeTruthy();
  expect(within(section).queryByText(/Productivité/)).toBeNull();
  client.clear();
});

it("performance absente sans la permission dédiée (lecture du référentiel seulement)", async () => {
  grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null }];
  const client = show();
  expect((await screen.findAllByText("Transports Fictifs SARL")).length).toBeGreaterThan(0);
  expect(screen.queryByRole("region", { name: "Performance des sous-traitants" })).toBeNull();
  expect(vi.mocked(read).mock.calls.some(([path]) => path === "/subcontractors/performance")).toBe(false);
  client.clear();
});

it("modification : vider l'objectif SLA l'efface (null explicite)", async () => {
  vi.mocked(read).mockImplementation((async (path: string) =>
    path === "/subcontractors/performance" ? performance : [{ ...active, availability_target_percent: "90.00" }]) as never);
  const client = show();
  fireEvent.click((await screen.findAllByRole("button", { name: "Modifier" }))[0]!);
  fireEvent.change(screen.getByLabelText("Objectif de disponibilité (SLA, %)"), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]![2]).toMatchObject({ body: { availability_target_percent: null } });
  client.clear();
});
