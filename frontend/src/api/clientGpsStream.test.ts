import { afterEach, expect, it, vi } from "vitest";
import { GpsStreamAccessDenied, setAccessToken, streamGpsSnapshots } from "./client";

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

function sseResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

it("lit un snapshot SSE authentifié sans jeton dans l'URL", async () => {
  setAccessToken("token-fictif");
  const fetchMock = vi.fn().mockResolvedValue(sseResponse([
    'event: snapshot\ndata: [{"vehicle_id":"v1","speed_kmh":45}]\n\n',
    ": heartbeat\n\n",
  ]));
  vi.stubGlobal("fetch", fetchMock);
  const received: { vehicle_id: string; speed_kmh: number }[][] = [];
  await streamGpsSnapshots<{ vehicle_id: string; speed_kmh: number }>(
    "site-1",
    (positions) => received.push(positions),
    new AbortController().signal,
  );
  expect(received).toEqual([[{ vehicle_id: "v1", speed_kmh: 45 }]]);
  expect(fetchMock).toHaveBeenCalledOnce();
  const [url, options] = fetchMock.mock.calls[0]!;
  expect(String(url)).toContain("site_id=site-1");
  expect(String(url)).not.toContain("token-fictif");
  expect(options.headers.Authorization).toBe("Bearer token-fictif");
});

it("n'accepte pas une réponse REST comme flux SSE", async () => {
  setAccessToken("token-fictif");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response("[]", { headers: { "Content-Type": "application/json" } }),
  ));
  await expect(streamGpsSnapshots(null, () => undefined, new AbortController().signal))
    .rejects.toThrow("Flux GPS indisponible");
});

it("refuse un snapshot mal formé et ne l'injecte pas dans la carte", async () => {
  setAccessToken("token-fictif");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([
    'event: snapshot\ndata: {"latitude":100}\n\n',
  ])));
  const onSnapshot = vi.fn();
  await expect(streamGpsSnapshots(null, onSnapshot, new AbortController().signal))
    .rejects.toThrow("Snapshot GPS invalide");
  expect(onSnapshot).not.toHaveBeenCalled();
});

it.each([403, 404])("ne réessaie pas un flux SSE refusé (HTTP %i)", async (status) => {
  setAccessToken("token-fictif");
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status }));
  vi.stubGlobal("fetch", fetchMock);
  const onSnapshot = vi.fn();
  await expect(streamGpsSnapshots("site-1", onSnapshot, new AbortController().signal))
    .rejects.toBeInstanceOf(GpsStreamAccessDenied);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(onSnapshot).not.toHaveBeenCalled();
});

it("interrompt le flux après révocation de session signalée par le serveur", async () => {
  setAccessToken("token-fictif");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse([
    'event: snapshot\ndata: [{"vehicle_id":"v1"}]\n\n',
    'event: session-ended\ndata: {}\n\n',
    'event: snapshot\ndata: [{"vehicle_id":"v2"}]\n\n',
  ])));
  const snapshots: unknown[][] = [];
  await expect(streamGpsSnapshots(null, (positions) => snapshots.push(positions), new AbortController().signal))
    .rejects.toBeInstanceOf(GpsStreamAccessDenied);
  expect(snapshots).toEqual([[{ vehicle_id: "v1" }]]);
});
