import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { call, read } from "../api/client";
import { HsePage } from "./HsePages";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "HSE", scope_type: "TENANT", site_id: null },
];
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ user_account_id: "moi", timezone: "Africa/Conakry", grants }),
}));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({
    siteId: "site-1",
    sites: [{ site_id: "site-1", code: "MINE", name: "Mine fictive", timezone: "Africa/Conakry" }],
    timezoneOf: () => "Africa/Conakry",
  }),
}));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
}));

const incident = {
  hse_incident_id: "inc-1",
  reference: "HSE-000001",
  site_id: "site-1",
  title: "Accrochage fictif",
  category: "VEHICLE_COLLISION",
  severity: "HIGH",
  occurred_at: "2026-10-30T08:00:00Z",
  vehicle_fleet_number: "PARC-FICTIF",
  open_actions: 1,
  overdue_actions: 1,
  status: "INVESTIGATING",
};
const summary = {
  since: "2026-08-04",
  incidents: 4,
  by_severity: {},
  by_category: {},
  injured: 1,
  lost_time_incidents: 1,
  open_incidents: 2,
  open_actions: 3,
  overdue_actions: 1,
  inspections: 5,
  failed_inspections: 2,
};
const myAction = {
  hse_corrective_action_id: "act-1",
  hse_incident_id: "inc-1",
  hse_inspection_id: null,
  parent_reference: "HSE-000001",
  title: "Baliser la zone",
  due_date: "2026-10-01",
  overdue: true,
  status: "OPEN",
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <HsePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) => {
    if (path === "/hse/summary") return summary;
    if (path === "/hse/corrective-actions") return { items: [myAction], total: 1, page: 1, page_size: 100 };
    return { items: [incident], total: 1, page: 1, page_size: 50 };
  }) as never);
  vi.mocked(call).mockResolvedValue({ data: { ...incident, hse_incident_id: "inc-2" }, etag: '"1"' } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null }];
});

it("affiche le registre, les indicateurs et mes actions en retard", async () => {
  const client = show();
  expect(await screen.findByText("Accrochage fictif", { exact: false })).toBeTruthy();
  expect(screen.getByText("Collision / accrochage d'engin")).toBeTruthy();
  expect(screen.getByText("1 en retard")).toBeTruthy();
  expect(await screen.findByText("Mes actions correctives à réaliser")).toBeTruthy();
  expect(screen.getByText("En retard")).toBeTruthy();
  expect(read).toHaveBeenCalledWith("/hse/incidents", expect.objectContaining({ query: expect.objectContaining({ site_id: "site-1", open_only: true }) }));
  client.clear();
});

it("un mécanicien peut déclarer mais ne charge pas le registre", async () => {
  grants = [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "site-1" }];
  const client = show();
  expect(screen.getByText(/le registre est réservé/)).toBeTruthy();
  expect(read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Déclarer un incident" }));
  fireEvent.change(screen.getByLabelText("Titre"), { target: { value: "Fuite d'huile" } });
  fireEvent.change(screen.getByLabelText("Description des faits"), { target: { value: "Flaque d'huile sous la pelle." } });
  fireEvent.change(screen.getByLabelText("Nature"), { target: { value: "SPILL" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer la déclaration" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  const [method, path, options] = vi.mocked(call).mock.calls[0]!;
  expect([method, path]).toEqual(["post", "/hse/incidents"]);
  expect(options).toMatchObject({
    body: { site_id: "site-1", category: "SPILL", title: "Fuite d'huile", injured_count: 0, vehicle_id: null },
  });
  await waitFor(() => expect(screen.queryByRole("form", { name: "Déclarer un incident" })).toBeNull());
  client.clear();
});
