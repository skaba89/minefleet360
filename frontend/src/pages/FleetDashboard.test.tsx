import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { FleetDashboard } from "./FleetDashboard";

vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: null, sites: [] }) }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), get: vi.fn(async (path: string) => path === "/vehicles/gps/latest" ? [{ recorded_at: "2026-10-29T12:00:00Z", received_at: "2026-10-29T12:00:00Z", speed_kmh: 30 }] : { total: 0, items: [] }) }));
afterEach(() => { cleanup(); vi.useRealTimers(); });

it("fait vieillir le compteur GPS même si les réponses successives du serveur ne changent pas", async () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-29T12:00:00Z"));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><FleetDashboard /></MemoryRouter></QueryClientProvider>);
  await act(async () => { await vi.advanceTimersByTimeAsync(100); });
  const value = () => screen.getByText("Signaux GPS récents").closest("a")?.querySelector("strong")?.textContent;
  expect(value()).toBe("1");
  await act(async () => { await vi.advanceTimersByTimeAsync(135_000); });
  expect(value()).toBe("0");
  client.clear();
});
