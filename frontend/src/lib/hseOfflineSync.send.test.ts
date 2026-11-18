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

  it("un relevé de compteur part vers l'URL de son engin, sans l'engin dans le corps", async () => {
    vi.mocked(request).mockResolvedValue({ data: { vehicle_meter_reading_id: "rel-1", value: 1050.5 } } as never);
    const meter = {
      ...entry("/vehicles/{vehicle_id}/meter-readings"),
      payload: {
        vehicle_id: "22222222-2222-4222-8222-222222222222",
        meter_kind: "ODOMETER_KM",
        value: 1050.5,
        read_at: "2026-11-16T05:00:00Z",
      },
    };
    expect(await defaultSyncDeps.send(meter)).toEqual({ id: "rel-1", reference: "relevé 1050.5" });
    expect(request).toHaveBeenCalledWith("/vehicles/22222222-2222-4222-8222-222222222222/meter-readings", {
      method: "POST",
      body: { meter_kind: "ODOMETER_KM", value: 1050.5, read_at: "2026-11-16T05:00:00Z" },
      idempotencyKey: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("un relevé dont l'engin n'est pas un identifiant n'est jamais envoyé (pas d'URL forgée)", async () => {
    const forged = { ...entry("/vehicles/{vehicle_id}/meter-readings"), payload: { vehicle_id: "../admin", value: 1 } };
    await expect(defaultSyncDeps.send(forged)).rejects.toThrow("Engin invalide");
    expect(request).not.toHaveBeenCalled();
  });

  it("un signalement de panne part vers /work-orders avec sa clé et l'heure du constat", async () => {
    vi.mocked(request).mockResolvedValue({ data: { work_order_id: "ot-1", reference: "OT-000001" } } as never);
    const breakdown = {
      ...entry("/work-orders"),
      payload: { vehicle_id: "v1", symptom_code: "BRAKES", immobilize: true, reported_at: "2026-11-16T05:00:00Z" },
    };
    expect(await defaultSyncDeps.send(breakdown)).toEqual({ id: "ot-1", reference: "OT-000001" });
    expect(request).toHaveBeenCalledWith("/work-orders", {
      method: "POST",
      body: breakdown.payload,
      idempotencyKey: "11111111-1111-4111-8111-111111111111",
    });
  });

  it("une route non prise en charge n'est jamais appelée", async () => {
    await expect(defaultSyncDeps.send(entry("/fuel/issues"))).rejects.toThrow("non prise en charge");
    expect(request).not.toHaveBeenCalled();
  });
});
