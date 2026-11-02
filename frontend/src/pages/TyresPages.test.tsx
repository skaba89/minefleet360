import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { call, read } from "../api/client";
import { TyrePage, TyresPage } from "./TyresPages";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "WORKSHOP_CHIEF", scope_type: "TENANT", site_id: null },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({ siteId: "s1", sites: [{ site_id: "s1", code: "MINE", name: "Mine" }], timezoneOf: () => "Africa/Conakry" }),
}));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const tyre = {
  tyre_id: "t1", site_id: "s1", serial_number: "SN-FICTIF-1", brand: "MarqueFictive", model: "Minier", size: "27.00R49",
  category: "DRIVE", spare_part_id: null, purchase_cost: null, currency: null, initial_tread_mm: "80.0",
  scrap_tread_mm: "10.0", nominal_pressure_kpa: 700, status: "MOUNTED", vehicle_id: "v1", vehicle_fleet_number: "CAM-1",
  position_code: "AV-G", mounted_at: "2026-10-01T08:00:00Z", retread_count: 0, last_tread_mm: "12.0",
  last_pressure_kpa: 560, last_inspected_at: null, scrap_reason: null, alerts: ["TREAD_LOW", "PRESSURE_DEVIATION"],
  total_cost: null, cost_complete: false, km_run: "0", hours_run: "0", cost_per_km: null, cost_per_hour: null,
  row_version: 3, events: [],
};

function show(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/pneus" element={<TyresPage />} />
          <Route path="/pneus/:tyreId" element={<TyrePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) =>
    path === "/tyres/stock"
      ? [{ site_id: "s1", size: "27.00R49", brand: "MarqueFictive", model: "Minier", spare_part_code: "PN-01", in_stock: 2, mounted: 1, in_repair: 0, alerts_in_stock: 1 }]
      : { items: [tyre], total: 1, page: 1, page_size: 50 }) as never);
  vi.mocked(call).mockResolvedValue({ data: tyre, etag: '"3"' } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "WORKSHOP_CHIEF", scope_type: "TENANT", site_id: null }];
});

it("liste les pneus avec position, alertes et coût insuffisant explicite", async () => {
  const client = show("/pneus");
  expect(await screen.findByText("CAM-1 · AV-G")).toBeTruthy();
  expect(screen.getByText("Sculpture proche de la limite")).toBeTruthy();
  expect(screen.getByText("Pression hors tolérance (±10 %)")).toBeTruthy();
  expect(screen.getByText("Données insuffisantes")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Enregistrer un pneu" })).toBeTruthy();
  expect(await screen.findByText("1 avec alerte")).toBeTruthy();
  expect(screen.getByText("PN-01")).toBeTruthy();
  client.clear();
});

it("un mécanicien démonte avec compteur et If-Match, sans action de gestion", async () => {
  grants = [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "s1" }];
  const client = show("/pneus/t1");
  fireEvent.click(await screen.findByRole("button", { name: "Démonter" }));
  expect(screen.queryByRole("button", { name: "Mettre au rebut" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Compteur kilométrique de l'engin"), { target: { value: "15000" } });
  const form = screen.getByRole("form", { name: "Démonter le pneu" });
  fireEvent.click(within(form).getByRole("button", { name: "Démonter" }));
  await waitFor(() => expect(call).toHaveBeenCalledWith("post", "/tyres/{tyre_id}/dismount", expect.anything()));
  const options = vi.mocked(call).mock.calls.find((c) => c[1] === "/tyres/{tyre_id}/dismount")![2] as { ifMatch: string; body: unknown };
  expect(options.ifMatch).toBe('"3"');
  expect(options.body).toMatchObject({ reason_code: "WEAR", odometer_km: "15000", hour_meter: null });
  client.clear();
});

it("exporte la liste filtrée au format CSV, toutes pages confondues", async () => {
  const created: Blob[] = [];
  globalThis.URL.createObjectURL = vi.fn((blob: Blob) => {
    created.push(blob);
    return "blob:export";
  });
  globalThis.URL.revokeObjectURL = vi.fn();
  const client = show("/pneus");
  fireEvent.click(await screen.findByRole("button", { name: "Exporter (CSV)" }));
  await waitFor(() => expect(created).toHaveLength(1));
  const text = await created[0]!.text();
  expect(text).toContain('"MarqueFictive";"SN-FICTIF-1"');
  expect(text).toContain("Sculpture proche de la limite ; Pression hors tolérance (±10 %)");
  expect(read).toHaveBeenCalledWith("/tyres", expect.objectContaining({ query: expect.objectContaining({ page: 1, page_size: 200 }) }));
  client.clear();
});
