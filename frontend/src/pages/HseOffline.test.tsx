import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { ApiError, call, read } from "../api/client";
import { queueIncident, syncAccount } from "../lib/hseOfflineSync";
import { listForAccount } from "../lib/offline-outbox";
import { OfflineFieldPage } from "./HseOffline";
import { HsePage } from "./HsePages";

const me = {
  workspace_code: "espace-fictif",
  user_account_id: "user-1",
  display_name: "Agent fictif",
  timezone: "Africa/Conakry",
  grants: [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "site-1" }],
};
const fieldProfile = {
  workspace_code: "espace-fictif",
  user_account_id: "user-1",
  display_name: "Agent fictif",
  timezone: "Africa/Conakry",
  sites: [{ site_id: "site-1", code: "MINE", name: "Mine fictive", timezone: "Africa/Conakry" }],
};
const retrySession = vi.fn();
vi.mock("../auth/AuthContext", () => ({
  useMe: () => me,
  useAuth: () => ({ fieldProfile, retrySession }),
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
vi.mock("../lib/hseOfflineSync", async (original) => ({
  ...(await original<typeof import("../lib/hseOfflineSync")>()),
  queueIncident: vi.fn(),
  syncAccount: vi.fn(),
}));
vi.mock("../lib/offline-outbox", async (original) => ({
  ...(await original<typeof import("../lib/offline-outbox")>()),
  listForAccount: vi.fn(),
  removeEntry: vi.fn(),
}));

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

function show(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

function fillAndSubmit(button: string) {
  fireEvent.change(screen.getByLabelText("Titre"), { target: { value: "Fuite d'huile" } });
  fireEvent.change(screen.getByLabelText("Description des faits"), { target: { value: "Flaque d'huile sous la pelle." } });
  fireEvent.click(screen.getByRole("button", { name: button }));
}

beforeEach(() => {
  vi.mocked(read).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 } as never);
  vi.mocked(listForAccount).mockResolvedValue([]);
  vi.mocked(queueIncident).mockResolvedValue({} as never);
  vi.mocked(syncAccount).mockResolvedValue({ kind: "done", synchronized: 0, rejected: 0, waiting: 0 });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  setOnline(true);
});

it("hors ligne, la déclaration est placée dans la file locale sans appel serveur", async () => {
  setOnline(false);
  const client = show(<HsePage />);
  fireEvent.click(screen.getByRole("button", { name: "Déclarer un incident" }));
  fillAndSubmit("Enregistrer sur l'appareil");
  await waitFor(() => expect(queueIncident).toHaveBeenCalledOnce());
  expect(call).not.toHaveBeenCalled();
  expect(vi.mocked(queueIncident).mock.calls[0]![0]).toEqual({ tenantId: "espace-fictif", userId: "user-1" });
  expect(vi.mocked(queueIncident).mock.calls[0]![1]).toMatchObject({ site_id: "site-1", title: "Fuite d'huile" });
  client.clear();
});

it("une réponse perdue en ligne bascule dans la file avec la même clé d'idempotence", async () => {
  vi.mocked(call).mockRejectedValue(
    new ApiError(0, { code: "NETWORK_ERROR", message_fr: "Connexion impossible", details: null, request_id: null }),
  );
  const client = show(<HsePage />);
  fireEvent.click(screen.getByRole("button", { name: "Déclarer un incident" }));
  fillAndSubmit("Enregistrer la déclaration");
  await waitFor(() => expect(queueIncident).toHaveBeenCalledOnce());
  const key = (vi.mocked(call).mock.calls[0]![2] as { idempotencyKey: string }).idempotencyKey;
  expect(key).toMatch(/^[0-9a-f-]{36}$/);
  expect(vi.mocked(queueIncident).mock.calls[0]![3]).toBe(key);
  client.clear();
});

it("un refus serveur n'est pas mis en file", async () => {
  vi.mocked(call).mockRejectedValue(
    new ApiError(422, { code: "REFERENCE_NOT_FOUND", message_fr: "Une ressource référencée est introuvable.", details: null, request_id: null }),
  );
  const client = show(<HsePage />);
  fireEvent.click(screen.getByRole("button", { name: "Déclarer un incident" }));
  fillAndSubmit("Enregistrer la déclaration");
  expect(await screen.findByText("Une ressource référencée est introuvable.")).toBeTruthy();
  expect(queueIncident).not.toHaveBeenCalled();
  client.clear();
});

it("affiche l'accusé de réception, les rejets et synchronise au retour du réseau", async () => {
  vi.mocked(listForAccount).mockResolvedValue([
    {
      operationId: "op-1", tenantId: "espace-fictif", userId: "user-1", siteId: "site-1", endpoint: "/hse/incidents",
      payload: { title: "Chute de pierres", category: "UNSAFE_CONDITION" }, createdAt: "2026-11-02T08:00:00Z",
      status: "synchronized", attempts: 1, serverId: "inc-9", serverReference: "HSE-000042",
    },
    {
      operationId: "op-2", tenantId: "espace-fictif", userId: "user-1", siteId: "site-1", endpoint: "/hse/incidents",
      payload: { title: "Site retiré", category: "OTHER" }, createdAt: "2026-11-02T08:05:00Z",
      status: "rejected", attempts: 1, errorCode: "PERMISSION_DENIED",
    },
    {
      operationId: "op-3", tenantId: "espace-fictif", userId: "user-1", siteId: "site-1", endpoint: "/hse/incidents",
      payload: { title: "En attente", category: "SPILL" }, createdAt: "2026-11-02T08:10:00Z",
      status: "pending", attempts: 0,
    },
  ]);
  const client = show(<HsePage />);
  expect(await screen.findByText("Synchronisé — HSE-000042")).toBeTruthy();
  expect(screen.getByText(/plus le droit de déclarer/)).toBeTruthy();
  expect(screen.getByText("En attente de synchronisation")).toBeTruthy();
  await waitFor(() => expect(syncAccount).toHaveBeenCalledWith({ tenantId: "espace-fictif", userId: "user-1" }));
  client.clear();
});

it("mode hors ligne au démarrage : déclaration seule, sans synchronisation ni appel API", async () => {
  setOnline(false);
  const client = show(<OfflineFieldPage />);
  expect(screen.getByText(/mode hors ligne/)).toBeTruthy();
  fillAndSubmit("Enregistrer sur l'appareil");
  await waitFor(() => expect(queueIncident).toHaveBeenCalledOnce());
  expect(await screen.findByText(/en attente de synchronisation/)).toBeTruthy();
  expect(syncAccount).not.toHaveBeenCalled();
  expect(read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Réessayer la connexion" }));
  expect(retrySession).toHaveBeenCalledOnce();
  client.clear();
});

it("après une tentative en échec, la resynchronisation repart à 5 s plutôt qu'à la cadence de 30 s", async () => {
  const pendingEntry = {
    operationId: "op-1", tenantId: "espace-fictif", userId: "user-1", siteId: "site-1", endpoint: "/hse/incidents",
    payload: { title: "En attente", category: "SPILL" }, createdAt: "2026-11-02T08:10:00Z",
    status: "pending" as const, attempts: 1, errorCode: "NETWORK_ERROR",
  };
  vi.useFakeTimers();
  try {
    vi.mocked(listForAccount).mockResolvedValue([pendingEntry]);
    // syncAccount laisse l'opération en attente : échec transitoire (réponse perdue).
    vi.mocked(syncAccount).mockResolvedValue({ kind: "done", synchronized: 0, rejected: 0, waiting: 1 });
    const client = show(<HsePage />);
    await vi.advanceTimersByTimeAsync(0);
    expect(syncAccount).toHaveBeenCalledTimes(1); // synchronisation immédiate à l'entrée en attente
    await vi.advanceTimersByTimeAsync(5_000);
    expect(syncAccount).toHaveBeenCalledTimes(2); // rejeu rapide après l'échec, pas d'attente de 30 s
    await vi.advanceTimersByTimeAsync(20_000);
    expect(syncAccount).toHaveBeenCalledTimes(6); // rejeu maintenu toutes les 5 s tant que l'envoi échoue
    await vi.advanceTimersByTimeAsync(5_000);
    expect(syncAccount).toHaveBeenCalledTimes(7);
    client.clear();
  } finally {
    vi.useRealTimers();
  }
});
