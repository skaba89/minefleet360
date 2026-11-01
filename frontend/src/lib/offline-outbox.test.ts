import { describe, expect, it } from "vitest";

import { assertAllowedEntry, enqueue, listPending } from "./offline-outbox";

const entry = {
  operationId: "f3d97219-6907-43af-a166-8aa61483e7fe",
  tenantId: "tenant-a",
  userId: "user-a",
  siteId: "site-a",
  endpoint: "/api/v1/work-orders",
  payload: { message: "test" },
  createdAt: "2026-11-01T12:00:00Z",
  status: "pending" as const,
  attempts: 0,
};

describe("outbox désactivée par défaut", () => {
  it("refuse une opération tant que sa route n'est pas autorisée", () => {
    expect(() => assertAllowedEntry(entry)).toThrow("indisponible");
  });

  it("ne persiste rien pour une route non autorisée", async () => {
    await expect(enqueue(entry)).rejects.toThrow("indisponible");
  });

  it("refuse de lire la file sans identité vérifiée", async () => {
    await expect(listPending({ tenantId: "", userId: "user-a", siteId: "site-a" })).rejects.toThrow("incomplète");
    await expect(listPending({ tenantId: "tenant-a", userId: "", siteId: "site-a" })).rejects.toThrow("incomplète");
  });
});
