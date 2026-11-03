import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { get, request } from "../api/client";
import { VehiclePreventiveStatus } from "./VehiclePreventiveStatus";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "WORKSHOP_CHIEF", scope_type: "SITE", site_id: "s1" },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "moi", timezone: "Africa/Conakry", grants }) }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  get: vi.fn(),
  request: vi.fn(),
}));

const status = {
  maintenance_plan_id: "p1", code: "VIDANGE", status: "UPCOMING", due_triggers: [], unknown_triggers: [],
  baseline_source: "DECLARATION", serviced_on: "2026-10-01", due_on: "2027-03-30",
  current_km: "10300.0", current_hours: null, remaining_km: "4700.0", remaining_hours: null,
  km_reliable: true, hours_reliable: true,
};
const unreliable = { ...status, maintenance_plan_id: "p2", code: "GRAISSAGE", status: "INSUFFICIENT_DATA", km_reliable: false, current_km: null };
const declaration = (id: string, by: string) => ({
  service_declaration_id: id, vehicle_id: "v1", site_id: "s1", plan_code: "VIDANGE", knowledge: "KNOWN",
  serviced_at: "2026-10-01T08:00:00Z", odometer_km: "10000.0", hour_meter: null, note: null, status: "PENDING",
  declared_by: by, declared_at: "2026-11-01T08:00:00Z", decided_by: null, decided_at: null, decision_note: null,
});

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><VehiclePreventiveStatus vehicleId="v1" siteId="s1" /></QueryClientProvider>);
}

beforeEach(() => {
  grants = [{ role_code: "WORKSHOP_CHIEF", scope_type: "SITE", site_id: "s1" }];
  vi.mocked(get).mockReset().mockImplementation(async (path: string) =>
    (path.endsWith("preventive-status") ? [status, unreliable] : [declaration("d-moi", "moi"), declaration("d-autre", "autre")]) as never,
  );
  vi.mocked(request).mockReset().mockResolvedValue({ data: {}, etag: null });
});
afterEach(cleanup);

it("affiche l'état calculé, le point de départ et un compteur non fiable", async () => {
  show();
  expect(await screen.findByText("À venir")).toBeTruthy();
  expect(screen.getAllByText(/Dernier entretien déclaré \(01\/10\/2026\)/)).toHaveLength(2);
  expect(screen.getByText("10300.0 (reste 4700.0)")).toBeTruthy();
  expect(screen.getByText(/Compteur non fiable/)).toBeTruthy();
});

it("n'offre pas l'approbation au déclarant et envoie la décision d'une autre déclaration", async () => {
  show();
  expect(await screen.findByText("À valider par une autre personne")).toBeTruthy();
  const approve = screen.getAllByRole("button", { name: "Approuver" });
  expect(approve).toHaveLength(1);
  fireEvent.click(approve[0]!);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/preventive-declarations/d-autre/decide", { method: "POST", body: { decision: "APPROVE", note: null } }),
  );
});

it("exige un motif pour rejeter", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Rejeter" }));
  const confirm = screen.getByRole("button", { name: "Confirmer le rejet" }) as HTMLButtonElement;
  expect(confirm.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Motif du rejet"), { target: { value: "carnet illisible" } });
  fireEvent.click(confirm);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/preventive-declarations/d-autre/decide", { method: "POST", body: { decision: "REJECT", note: "carnet illisible" } }),
  );
});

it("déclare un dernier entretien inconnu sans date ni compteur", async () => {
  show();
  fireEvent.click((await screen.findAllByRole("button", { name: "Déclarer le dernier entretien" }))[0]!);
  fireEvent.click(screen.getByLabelText(/Inconnu/));
  fireEvent.click(screen.getByRole("button", { name: "Envoyer pour validation" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/preventive-declarations", {
      method: "POST",
      body: { vehicle_id: "v1", plan_code: "VIDANGE", knowledge: "UNKNOWN", serviced_at: null, odometer_km: null, hour_meter: null, note: null },
    }),
  );
});

it("lecteur sans droit de gestion : ni déclaration ni décision", async () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  show();
  expect(await screen.findByText("À venir")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Déclarer le dernier entretien" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Approuver" })).toBeNull();
});
