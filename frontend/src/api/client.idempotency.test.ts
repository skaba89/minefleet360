import { afterEach, expect, it, vi } from "vitest";

import { request, setAccessToken } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  setAccessToken(null);
});

it("transmet une clé d'idempotence explicite au serveur", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
    status: 200, headers: { "Content-Type": "application/json" },
  }));
  vi.stubGlobal("fetch", fetchMock);
  await request("/work-orders/00000000-0000-4000-8000-000000000001/progress", {
    method: "POST",
    ifMatch: '"3"',
    idempotencyKey: "draft-00000000-0000-4000-8000-000000000001",
    body: { action: "NOTE", work_done: "Inspection" },
  });
  const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
  const headers = options.headers as Record<string, string>;
  expect(headers["Idempotency-Key"]).toBe("draft-00000000-0000-4000-8000-000000000001");
  expect(headers["If-Match"]).toBe('"3"');
});

it("n'invente pas de clé pour les mutations ordinaires", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  await request("/auth/logout", { method: "POST" });
  const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
  expect((options.headers as Record<string, string>)["Idempotency-Key"]).toBeUndefined();
});
