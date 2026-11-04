import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { get, request } from "../api/client";
import { GpsAlertsPage } from "./GpsAlertsPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), get: vi.fn(), request: vi.fn() }));

const alert = (id: string, extra: object) => ({
  gps_alert_id: id, site_id: "s1", vehicle_id: `v-${id}`, fleet_number: `CAM-${id}`, kind: "OVERSPEED",
  opened_at: "2026-11-04T08:00:00Z", last_measured_at: "2026-11-04T08:02:00Z", closed_at: null, latitude: 10, longitude: -12,
  speed_limit_kmh: "50.0", peak_speed_kmh: 72.5, site_geofence_id: null, geofence_name: null,
  acknowledged_by: null, acknowledged_at: null, acknowledgement_note: null, ...extra,
});

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><GpsAlertsPage /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
  vi.mocked(get).mockReset().mockImplementation(async (path: string) =>
    (path.endsWith("gps-policy")
      ? { site_id: "s1", speed_limit_kmh: "50.0", signal_loss_minutes: null, updated_at: null }
      : { items: [alert("1", {}), alert("2", { kind: "RESTRICTED_ZONE_ENTRY", closed_at: "2026-11-04T08:00:00Z", speed_limit_kmh: null, peak_speed_kmh: null, geofence_name: "Zone explosifs" })], total: 2 }) as never,
  );
  vi.mocked(request).mockReset().mockResolvedValue({ data: {}, etag: null });
  vi.stubGlobal("prompt", () => "conducteur prévenu");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("liste les alertes avec leur détail mesuré et la limite du site", async () => {
  show();
  expect(await screen.findByText("CAM-1")).toBeTruthy();
  expect(screen.getByText("72.5 km/h au maximum pour 50.0 km/h autorisés")).toBeTruthy();
  expect(screen.getByText("En cours")).toBeTruthy();
  expect(screen.getByText("Entrée en zone interdite")).toBeTruthy();
  expect(screen.getByText("Zone explosifs")).toBeTruthy();
  expect(await screen.findByText(/Alerte au-delà de 50.0 km\/h mesurés\. Perte de signal non surveillée\./)).toBeTruthy();
  expect(get).toHaveBeenCalledWith("/gps/alerts", { site_id: "s1", unacknowledged: true, page_size: 100 });
});

it("prend une alerte en compte avec une remarque et règle la limite", async () => {
  show();
  fireEvent.click((await screen.findAllByRole("button", { name: "Prendre en compte" }))[0]!);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/gps/alerts/1/acknowledge", { method: "POST", body: { note: "conducteur prévenu" } }),
  );
  fireEvent.change(screen.getByLabelText(/Nouvelle limite/), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText(/Perte de signal après/), { target: { value: "20" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/sites/s1/gps-policy", { method: "PUT", body: { speed_limit_kmh: null, signal_loss_minutes: 20 } }),
  );
});

it("auditeur : lecture seule", async () => {
  grants = [{ role_code: "AUDITOR", scope_type: "TENANT", site_id: null }];
  show();
  expect(await screen.findByText("CAM-1")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Prendre en compte" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Enregistrer" })).toBeNull();
});

it("affiche une perte de signal avec l'heure de la dernière position mesurée", async () => {
  vi.mocked(get).mockImplementation(async (path: string) =>
    (path.endsWith("gps-policy")
      ? { site_id: "s1", speed_limit_kmh: null, signal_loss_minutes: 15, updated_at: null }
      : { items: [alert("3", { kind: "SIGNAL_LOST", speed_limit_kmh: null, peak_speed_kmh: null, last_measured_at: "2026-11-04T07:40:00Z" })], total: 1 }) as never,
  );
  show();
  expect(await screen.findByText("Perte de signal")).toBeTruthy();
  expect(screen.getByText("Dernière position mesurée 04/11/2026 07:40")).toBeTruthy();
  expect(await screen.findByText(/Perte de signal signalée après 15 min sans position/)).toBeTruthy();
});
