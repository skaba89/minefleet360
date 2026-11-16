import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "../api/client";
import { defaultSyncDeps } from "./hseOfflineSync";
import type { OutboxEntry } from "./offline-outbox";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  request: vi.fn(),
}));

function entry(endpoint: string): OutboxEntry {
  return {
    operationId: "11111111-1111-4111-8111-111111111111",
    tenantId: "espace-a",
    userId: "user-a",
    siteId: "site-1",
    endpoint,
    payload: { site_id: "site-1" },
    createdAt: "2026-11-16T06:00:00Z",
    status: "pending",
    attempts: 0,
    summary: "libellé local",
  };
}

afterEach(() => vi.clearAllMocks());

describe("envoi d'une opération hors ligne vers sa route", () => {
  it("une inspection part vers /hse/inspections avec sa clé, sans le libellé local", async () => {
    vi.mocked(request).mockResolvedValue({ data: { hse_inspection_id: "ins-1", reference: "INS-000001" } } as never);
    const ack = await defaultSyncDeps.send(entry("/hse/inspections"));
    expect(ack).toEqual({ id: "ins-1", reference: "INS-000001" });
    expect(request).toHaveBeenCalledWith("/hse/inspections", {
      method: "POST",
      body: { site_id: "site-1" },
      idempotencyKey: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("un accusé d'inspection incomplet est une erreur (jamais « synchronisé »)", async () => {
    vi.mocked(request).mockResolvedValue({ data: { reference: "INS-000001" } } as never);
    await expect(defaultSyncDeps.send(entry("/hse/inspections"))).rejects.toThrow("incomplet");
  });

  it("une déclaration d'incident garde son contrat d'origine", async () => {
    vi.mocked(request).mockResolvedValue({ data: { hse_incident_id: "inc-1", reference: "HSE-000001" } } as never);
    expect(await defaultSyncDeps.send(entry("/hse/incidents"))).toEqual({ id: "inc-1", reference: "HSE-000001" });
  });

  it("une route non prise en charge n'est jamais appelée", async () => {
    await expect(defaultSyncDeps.send(entry("/work-orders"))).rejects.toThrow("non prise en charge");
    expect(request).not.toHaveBeenCalled();
  });
});
