import { describe, expect, it, vi } from "vitest";

import { call, read } from "./client";

// Vérifications de typage (tsc) : un paramètre inconnu de l'API ne compile pas.
function typingContract() {
  void read("/drivers", { query: { q: "dupont", status: "ACTIVE" } });
  // @ts-expect-error le paramètre de recherche des conducteurs s'appelle `q`
  void read("/drivers", { query: { search: "dupont" } });
  // @ts-expect-error statut hors énumération
  void read("/vehicles", { query: { status: "BROKEN" } });
  void call("post", "/vehicles/{vehicle_id}/status", {
    path: { vehicle_id: "x" },
    body: { status: "IN_MAINTENANCE" },
    ifMatch: '"1"',
  });
  // @ts-expect-error route sans PATCH
  void call("patch", "/vehicle-assignments", {});
}
void typingContract;

describe("appel typé", () => {
  it("remplace les paramètres de chemin et transmet requête, corps et If-Match", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { ETag: '"2"' } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const res = await call("post", "/vehicles/{vehicle_id}/status", {
      path: { vehicle_id: "a b" },
      body: { status: "IN_MAINTENANCE" },
      ifMatch: '"1"',
    });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/vehicles/a%20b/status");
    expect((init?.headers as Record<string, string>)["If-Match"]).toBe('"1"');
    expect(res.etag).toBe('"2"');
    await read("/drivers", { query: { q: "dupont", page: 2 } });
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/v1/drivers?q=dupont&page=2");
  });
});
