import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { read } from "../api/client";
import { FuelDashboard } from "./FuelDashboard";

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  read: vi.fn(),
}));

const response = {
  period_start: "2026-10-01T00:00:00Z",
  period_end: "2026-10-31T00:00:00Z",
  distributed_liters: "1250.000",
  received_liters: "1800.000",
  stocktake_variance_liters: "-12.500",
  qualified_anomaly_variance_liters: "42.000",
  open_anomaly_cases: 3,
  closed_anomaly_cases: 7,
  average_resolution_hours: "36.00",
  active_stock_alerts: 2,
  unacknowledged_stock_alerts: 1,
  vehicle_consumption: [{ vehicle_id: "v1", vehicle_fleet_number: "GN-1234-AB", site_id: "s1", liters: "450.000" }],
  site_consumption: [{ site_id: "s1", site_code: "MINE", site_name: "Mine principale", liters: "1250.000" }],
  daily_trend: [
    { day: "2026-10-29", distributed_liters: "400.000", received_liters: "600.000" },
    { day: "2026-10-30", distributed_liters: "850.000", received_liters: "1200.000" },
  ],
};

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("affiche les KPI, tendances et points de vigilance issus du serveur", async () => {
  vi.mocked(read).mockResolvedValue(response as never);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><FuelDashboard siteId="s1" enabled /></QueryClientProvider>);

  const metricLabel = (name: string) => screen.getByText(name).closest(".metric-card")?.getAttribute("aria-label");
  await waitFor(() => expect(metricLabel("Volumes distribués")).toBe("Volumes distribués : 1 250 L"));
  expect(metricLabel("Volumes réceptionnés")).toBe("Volumes réceptionnés : 1 800 L");
  expect(metricLabel("Anomalies actives")).toBe("Anomalies actives : 3");
  expect(metricLabel("Alertes de stock")).toBe("Alertes de stock : 2");
  expect(screen.getByRole("img", { name: "Tendance quotidienne des volumes distribués et réceptionnés" })).toBeTruthy();
  expect(screen.getByRole("img", { name: "Consommation de carburant par site" })).toBeTruthy();
  expect(screen.getByText("GN-1234-AB")).toBeTruthy();
  expect(screen.getByText("1,5 j")).toBeTruthy();
  expect(screen.getByText("-12,5 L")).toBeTruthy();

  expect(read).toHaveBeenCalledWith("/fuel/dashboard", expect.objectContaining({ query: expect.objectContaining({ site_id: "s1" }) }));
  fireEvent.change(screen.getByLabelText("Période du tableau de bord"), { target: { value: "7" } });
  await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  client.clear();
});

it("ne lance aucun appel sans permission de lecture", () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(<QueryClientProvider client={client}><FuelDashboard siteId={null} enabled={false} /></QueryClientProvider>);
  expect(container.innerHTML).toBe("");
  expect(read).not.toHaveBeenCalled();
  client.clear();
});
