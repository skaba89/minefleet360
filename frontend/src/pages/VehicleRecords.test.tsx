import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError, call, read } from "../api/client";
import { queueMeterReading } from "../lib/hseOfflineSync";
import { Meters } from "./VehicleRecords";

let online = true;
vi.mock("../lib/connectivity", () => ({ useConnectivity: () => online }));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({
    workspace_code: "espace-a",
    user_account_id: "u1",
    timezone: "Africa/Conakry",
    grants: [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }],
  }),
}));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("./HseOffline", () => ({ OfflineIncidentQueue: () => null }));
vi.mock("../lib/hseOfflineSync", async (original) => ({
  ...(await original<typeof import("../lib/hseOfflineSync")>()),
  queueMeterReading: vi.fn(),
}));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const vehicle = { vehicle_id: "v1", site_id: "s1", fleet_number: "CAM-12", status: "ACTIVE" };
const category = { has_odometer: true, has_hour_meter: false };

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <Meters vehicle={vehicle as never} category={category as never} />
    </QueryClientProvider>,
  );
  return client;
}

async function enterReading() {
  fireEvent.click(await screen.findByRole("button", { name: "Nouveau relevé" }));
  fireEvent.change(screen.getByLabelText("Valeur relevée"), { target: { value: "1050.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer le relevé" }));
}

beforeEach(() => {
  vi.mocked(read).mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 } as never);
  vi.mocked(queueMeterReading).mockResolvedValue({} as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  online = true;
});

it("hors ligne : le relevé est mis en file avec l'engin, le site et l'heure du relevé", async () => {
  online = false;
  const client = show();
  await enterReading();
  await waitFor(() => expect(queueMeterReading).toHaveBeenCalledOnce());
  const [account, siteId, vehicleId, body, summary] = vi.mocked(queueMeterReading).mock.calls[0]!;
  expect(account).toEqual({ tenantId: "espace-a", userId: "u1" });
  expect([siteId, vehicleId]).toEqual(["s1", "v1"]);
  expect(body).toMatchObject({ meter_kind: "ODOMETER_KM", value: 1050.5 });
  expect(typeof body.read_at).toBe("string");
  expect(summary).toContain("CAM-12");
  expect(call).not.toHaveBeenCalled();
  client.clear();
});

it("en ligne : envoi direct avec une clé d'idempotence ; réponse perdue → même clé mise en file", async () => {
  vi.mocked(call).mockRejectedValue(new ApiError(0, { code: "NETWORK_ERROR", message_fr: "Réseau indisponible", details: [], request_id: null }) as never);
  const client = show();
  await enterReading();
  await waitFor(() => expect(queueMeterReading).toHaveBeenCalledOnce());
  const key = (vi.mocked(call).mock.calls[0]![2] as { idempotencyKey: string }).idempotencyKey;
  expect(key).toMatch(/^[0-9a-f-]{36}$/);
  expect(vi.mocked(queueMeterReading).mock.calls[0]![6]).toBe(key);
  client.clear();
});

it("un refus métier du serveur n'est jamais mis en file", async () => {
  vi.mocked(call).mockRejectedValue(new ApiError(422, { code: "VALIDATION_ERROR", message_fr: "Relevé en baisse", details: [], request_id: null }) as never);
  const client = show();
  await enterReading();
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(queueMeterReading).not.toHaveBeenCalled();
  client.clear();
});
