import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { get, request } from "../api/client";
import { SitePreventiveDues } from "./SitePreventiveDues";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  get: vi.fn(),
  request: vi.fn(),
}));

const due = (id: string, extra: object) => ({
  maintenance_due_id: id, maintenance_plan_id: "p", plan_code: "VIDANGE", vehicle_id: `v-${id}`, fleet_number: `CAM-${id}`,
  site_id: "s1", trigger_kind: "DAYS", status: "DUE", due_on: "2026-11-01", due_meter: null,
  evaluated_at: "2026-11-03T08:00:00Z", work_order_id: null, ...extra,
});

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><SitePreventiveDues siteId="s1" /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  grants = [{ role_code: "WORKSHOP_CHIEF", scope_type: "SITE", site_id: "s1" }];
  vi.mocked(get).mockReset().mockResolvedValue({
    items: [due("1", {}), due("2", { trigger_kind: "INITIAL", status: "SCHEDULED", work_order_id: "ot-2" })],
    total: 2,
  } as never);
  vi.mocked(request).mockReset().mockResolvedValue({
    data: { plans_evaluated: 5, due_now: 2, created: 1, already_recorded: 1, upcoming: 2, insufficient_data: 1 },
    etag: null,
  });
});
afterEach(cleanup);

it("liste les échéances ouvertes du site avec planification ou lien vers l'OT", async () => {
  show();
  expect(await screen.findByText("CAM-1")).toBeTruthy();
  expect(get).toHaveBeenCalledWith("/preventive-dues", { site_id: "s1", open_only: true, page_size: 200 });
  expect(screen.getByText("Entretien initial")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Voir l'OT" }).getAttribute("href")).toBe("/atelier/ot-2");
  fireEvent.click(screen.getByRole("button", { name: "Planifier l'entretien" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("/preventive-dues/1/schedule", { method: "POST" }));
});

it("évalue les échéances du site et résume le résultat", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Évaluer les échéances" }));
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith("/preventive-dues/evaluate", { method: "POST", body: { site_id: "s1" } }),
  );
  expect(await screen.findByText(/5 plan\(s\) évalué\(s\) : 1 nouvelle\(s\) échéance\(s\)/)).toBeTruthy();
});

it("lecteur : ni évaluation ni planification", async () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  show();
  expect(await screen.findByText("CAM-1")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Évaluer les échéances" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Planifier l'entretien" })).toBeNull();
});
