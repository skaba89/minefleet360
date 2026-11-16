import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { ApiError, call, read } from "../api/client";
import { queueInspection, syncAccount } from "../lib/hseOfflineSync";
import { HSE_INSPECTION_ENDPOINT, listForAccount } from "../lib/offline-outbox";
import { HseInspectionsPage } from "./HseInspectionsPages";

/** Inspection HSE hors ligne (phase 3, tranche 2) : même file et même contrat que les déclarations d'incident. */
const me = {
  workspace_code: "espace-fictif",
  user_account_id: "user-1",
  display_name: "Agent fictif",
  timezone: "Africa/Conakry",
  grants: [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "site-1" }],
};
vi.mock("../auth/AuthContext", () => ({ useMe: () => me }));
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
  queueInspection: vi.fn(),
  syncAccount: vi.fn(),
}));
vi.mock("../lib/offline-outbox", async (original) => ({
  ...(await original<typeof import("../lib/offline-outbox")>()),
  listForAccount: vi.fn(),
  removeEntry: vi.fn(),
}));

const template = {
  hse_checklist_template_id: "tpl-1",
  code: "PRE",
  version: 2,
  name: "Prise de poste",
  target_type: "PRE_SHIFT",
  active: true,
  created_at: "2026-11-01T08:00:00Z",
  items: [
    { key: "epi", label: "EPI portés", critical: true },
    { key: "radio", label: "Radio testée", critical: false },
  ],
};

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <HseInspectionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

async function fillAndSubmit(button: string) {
  fireEvent.click(screen.getByRole("button", { name: "Réaliser une inspection" }));
  // La checklist provient du cache de requêtes chargé avant la coupure (tranche 2 : coupure en cours de session).
  await screen.findByRole("option", { name: /Prise de poste/ });
  fireEvent.change(screen.getByLabelText("Checklist"), { target: { value: "tpl-1" } });
  fireEvent.click(screen.getByRole("button", { name: button }));
}

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) =>
    path === "/hse/checklist-templates" ? [template] : { items: [], total: 0, page: 1, page_size: 50 }) as never);
  vi.mocked(listForAccount).mockResolvedValue([]);
  vi.mocked(queueInspection).mockResolvedValue({} as never);
  vi.mocked(syncAccount).mockResolvedValue({ kind: "done", synchronized: 0, rejected: 0, waiting: 0 });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  setOnline(true);
});

it("hors ligne, l'inspection est placée dans la file locale sans appel serveur", async () => {
  setOnline(false);
  const client = show();
  await fillAndSubmit("Enregistrer sur l'appareil");
  await waitFor(() => expect(queueInspection).toHaveBeenCalledOnce());
  expect(call).not.toHaveBeenCalled();
  const [account, body, summary] = vi.mocked(queueInspection).mock.calls[0]!;
  expect(account).toEqual({ tenantId: "espace-fictif", userId: "user-1" });
  expect(body).toMatchObject({
    site_id: "site-1",
    hse_checklist_template_id: "tpl-1",
    answers: [
      { item_key: "epi", result: "COMPLIANT", comment: null },
      { item_key: "radio", result: "COMPLIANT", comment: null },
    ],
  });
  // Le libellé local n'appartient pas au corps envoyé au serveur (schéma strict côté API).
  expect(summary).toBe("Prise de poste v2");
  expect(body).not.toHaveProperty("summary");
  client.clear();
});

it("une réponse perdue en ligne bascule dans la file avec la même clé d'idempotence", async () => {
  vi.mocked(call).mockRejectedValue(
    new ApiError(0, { code: "NETWORK_ERROR", message_fr: "Connexion impossible", details: null, request_id: null }),
  );
  const client = show();
  await fillAndSubmit("Enregistrer l'inspection");
  await waitFor(() => expect(queueInspection).toHaveBeenCalledOnce());
  const [method, path, options] = vi.mocked(call).mock.calls[0]!;
  expect([method, path]).toEqual(["post", "/hse/inspections"]);
  const key = (options as { idempotencyKey: string }).idempotencyKey;
  expect(key).toMatch(/^[0-9a-f-]{36}$/);
  expect(vi.mocked(queueInspection).mock.calls[0]![4]).toBe(key);
  client.clear();
});

it("un refus serveur n'est pas mis en file", async () => {
  vi.mocked(call).mockRejectedValue(
    new ApiError(422, {
      code: "REFERENCE_NOT_FOUND",
      message_fr: "Une ressource référencée est introuvable.",
      details: null,
      request_id: null,
    }),
  );
  const client = show();
  await fillAndSubmit("Enregistrer l'inspection");
  expect(await screen.findByText("Une ressource référencée est introuvable.")).toBeTruthy();
  expect(queueInspection).not.toHaveBeenCalled();
  client.clear();
});

it("la file affiche l'inspection synchronisée avec un lien vers l'inspection serveur", async () => {
  vi.mocked(listForAccount).mockResolvedValue([
    {
      operationId: "op-1",
      tenantId: "espace-fictif",
      userId: "user-1",
      siteId: "site-1",
      endpoint: HSE_INSPECTION_ENDPOINT,
      payload: { site_id: "site-1" },
      createdAt: "2026-11-16T06:00:00Z",
      status: "synchronized",
      attempts: 1,
      serverId: "ins-9",
      serverReference: "INS-000009",
      summary: "Prise de poste v2",
    },
  ]);
  me.grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null as unknown as string }];
  const client = show();
  expect(await screen.findByText("Inspection — Prise de poste v2")).toBeTruthy();
  expect(screen.getByText("Synchronisé — INS-000009")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Ouvrir" }).getAttribute("href")).toBe("/hse/inspections/ins-9");
  me.grants = [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "site-1" }];
  client.clear();
});
