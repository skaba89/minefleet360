import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { call } from "../api/client";
import { parseCoordinates, VehicleTrackPanel } from "./GpsHistory";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "HSE", scope_type: "TENANT", site_id: null },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", sites: [], timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), call: vi.fn(), read: vi.fn() }));

const track = {
  vehicle_id: "v1", period_start: "2026-11-02T00:00:00Z", period_end: "2026-11-02T06:00:00Z", signal: "LOST",
  last_recorded_at: "2026-11-02T05:00:00Z", truncated: false, distance_km: 2.78, late_points: 1, ignored_points: 2,
  points: [
    { latitude: 9.49, longitude: -13.705, speed_kmh: null, accuracy_m: 10, recorded_at: "2026-11-02T03:00:00Z", received_at: "2026-11-02T03:00:00Z", late: false, source: "TRACKER" },
    { latitude: 9.515, longitude: -13.705, speed_kmh: null, accuracy_m: 10, recorded_at: "2026-11-02T03:32:00Z", received_at: "2026-11-02T03:32:00Z", late: false, source: "TRACKER" },
  ],
  gaps: [{ start: "2026-11-02T03:32:00Z", end: "2026-11-02T04:14:00Z", minutes: 42 }],
  stops: [{ start: "2026-11-02T03:08:00Z", end: "2026-11-02T03:28:00Z", minutes: 20, latitude: 9.505, longitude: -13.705 }],
  geofence_events: [
    { vehicle_id: "v1", vehicle_fleet_number: "CAM-1", site_geofence_id: "g1", geofence_name: "Fosse nord", geofence_kind: "LOADING_AREA", event_type: "ENTER", occurred_at: "2026-11-02T03:06:00Z" },
  ],
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><VehicleTrackPanel vehicleId="v1" siteId="s1" /></QueryClientProvider>);
  return client;
}

beforeEach(() => vi.mocked(call).mockResolvedValue({ data: track, etag: null } as never));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null }];
});

it("exige une finalité puis affiche zones, arrêts, interruptions et tracé", async () => {
  const client = show();
  fireEvent.click(screen.getByRole("button", { name: "Afficher le trajet" }));
  expect(call).not.toHaveBeenCalled(); // finalité obligatoire (champ requis)
  fireEvent.change(screen.getByLabelText("Finalité"), { target: { value: "INCIDENT_INVESTIGATION" } });
  fireEvent.click(screen.getByRole("button", { name: "Afficher le trajet" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  const options = vi.mocked(call).mock.calls[0]![2] as { query: { purpose: string } };
  expect(options.query.purpose).toBe("INCIDENT_INVESTIGATION");
  expect(await screen.findByText(/Entrée : Fosse nord/)).toBeTruthy();
  expect(screen.getByText(/42 min sans position/)).toBeTruthy();
  expect(screen.getByText("Signal perdu")).toBeTruthy();
  expect(screen.getByRole("region", { name: "Relecture du trajet" })).toBeTruthy();
  client.clear();
});

it("n'affiche rien sans le droit d'historique", () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  const client = show();
  expect(screen.queryByRole("region", { name: "Historique de trajet" })).toBeNull();
  client.clear();
});

it("convertit les sommets saisis en latitude, longitude vers l'ordre GeoJSON", () => {
  expect(parseCoordinates("9.50, -13.71\n9.50;-13.70\n 9.51 -13.70 \n")).toEqual([[-13.71, 9.5], [-13.7, 9.5], [-13.7, 9.51]]);
  expect(() => parseCoordinates("abc")).toThrow("Ligne invalide");
});
