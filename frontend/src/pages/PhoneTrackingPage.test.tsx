import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { get, request } from "../api/client";
import { PhoneTrackingPage } from "./PhoneTrackingPage";

vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ timezone: "Africa/Conakry", grants: [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }] }) }));
vi.mock("../api/client", async (original) => ({ ...await original<typeof import("../api/client")>(), get: vi.fn(), request: vi.fn() }));
const share = { phone_share_id: "share", vehicle_id: "vehicle", started_at: new Date().toISOString(), expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString() };
let success: PositionCallback;
let failure: PositionErrorCallback | null;
const locate = vi.fn((ok: PositionCallback, fail?: PositionErrorCallback | null) => { success = ok; failure = fail ?? null; });
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { ...render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/mon-suivi?vehicle=vehicle"]}><PhoneTrackingPage /></MemoryRouter></QueryClientProvider>), client };
}
beforeEach(() => {
  vi.clearAllMocks(); vi.mocked(get).mockReset(); vi.mocked(request).mockReset(); vi.stubGlobal("isSecureContext", true);
  Object.defineProperty(navigator, "geolocation", { configurable: true, value: { getCurrentPosition: locate } });
  vi.mocked(get).mockResolvedValue([{ vehicle_id: "vehicle", fleet_number: "PARC-FICTIF", registration_number: null, site_id: "site" }]);
  vi.mocked(request).mockImplementation(async (path) => ({ data: path === "/me/gps/shares" ? share : undefined, etag: null }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Object.defineProperty(navigator, "onLine", { configurable: true, value: true }); });
it("demande le consentement et coupe les envois après l'arrêt", async () => {
  setup();
  const start = await screen.findByRole("button", { name: "Démarrer le partage" });
  expect((start as HTMLButtonElement).disabled).toBe(true); expect(locate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(start);
  await waitFor(() => expect(locate).toHaveBeenCalledOnce());
  success({ timestamp: Date.now(), coords: { latitude: 9.5, longitude: -13.7, accuracy: 12, speed: null } } as GeolocationPosition);
  await screen.findByText(/Partage actif · précision/);
  const call = vi.mocked(request).mock.calls.find(([p]) => p.endsWith("/positions"));
  expect(call?.[1]?.body).toMatchObject({ latitude: 9.5, longitude: -13.7, accuracy_m: 12, speed_kmh: null });
  fireEvent.click(screen.getByRole("button", { name: "Arrêter le partage" }));
  await screen.findByText("Partage arrêté et confirmé par le serveur");
  const count = vi.mocked(request).mock.calls.filter(([p]) => p.endsWith("/positions")).length;
  success({ timestamp: Date.now(), coords: { latitude: 10, longitude: -13, accuracy: 10, speed: 4 } } as GeolocationPosition);
  expect(vi.mocked(request).mock.calls.filter(([p]) => p.endsWith("/positions"))).toHaveLength(count);
});
it("arrête le partage serveur quand la permission navigateur est refusée", async () => {
  setup(); await screen.findByRole("button", { name: "Démarrer le partage" });
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Démarrer le partage" }));
  await waitFor(() => expect(locate).toHaveBeenCalledOnce()); failure?.({ code: 1 } as GeolocationPositionError);
  expect((await screen.findByRole("alert")).textContent).toContain("Localisation refusée");
  expect(vi.mocked(request).mock.calls.some(([p]) => p === "/me/gps/shares/share/stop")).toBe(true);
  expect(vi.mocked(request).mock.calls.some(([p]) => p.endsWith("/positions"))).toBe(false);
});
it("garde l'arrêt accessible si la liste des véhicules devient indisponible", async () => {
  const view = setup(); await screen.findByRole("button", { name: "Démarrer le partage" });
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Démarrer le partage" }));
  await waitFor(() => expect(locate).toHaveBeenCalledOnce());
  vi.mocked(get).mockRejectedValue(new Error("réseau indisponible"));
  await act(async () => { await view.client.invalidateQueries({ queryKey: ["gps-sharing-vehicles"] }); });
  fireEvent.click(screen.getByRole("button", { name: "Arrêter le partage" }));
  await screen.findByText("Partage arrêté et confirmé par le serveur");
  expect(vi.mocked(request).mock.calls.some(([p]) => p.endsWith("/stop"))).toBe(true);
});
it("ne démarre pas le GPS si la création finit après avoir quitté la page", async () => {
  let finish: (value: { data: typeof share; etag: null }) => void = () => undefined;
  vi.mocked(request).mockImplementation((path) => path === "/me/gps/shares" ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve({ data: undefined, etag: null }));
  const view = setup(); await screen.findByRole("button", { name: "Démarrer le partage" });
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Démarrer le partage" }));
  await waitFor(() => expect(request).toHaveBeenCalledOnce()); view.unmount(); finish({ data: share, etag: null });
  await waitFor(() => expect(vi.mocked(request).mock.calls.some(([p]) => p.endsWith("/stop"))).toBe(true));
  expect(locate).not.toHaveBeenCalled();
});

it("bloque le démarrage sans réseau et annonce l'absence de mise en attente", async () => {
  setup();
  await screen.findByRole("button", { name: "Démarrer le partage" });
  Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
  act(() => window.dispatchEvent(new Event("offline")));
  expect(screen.getByText(/Connexion absente : les relevés restent temporairement en mémoire/)).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox"));
  const button = screen.getByRole("button", { name: "Démarrer le partage" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(vi.mocked(request)).not.toHaveBeenCalled();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
  act(() => window.dispatchEvent(new Event("online")));
  expect(button.disabled).toBe(false);
});

it("conserve des relevés uniquement en mémoire durant une coupure sans requête serveur", async () => {
  setup();
  await waitFor(() => expect(vi.mocked(get)).toHaveBeenCalled());
  await screen.findByRole("button", { name: "Démarrer le partage" });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Démarrer le partage" }));
  await waitFor(() => expect(locate).toHaveBeenCalledOnce());
  Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
  act(() => window.dispatchEvent(new Event("offline")));
  act(() => success({
    timestamp: Date.now(),
    coords: { latitude: 9.5, longitude: -13.7, accuracy: 12, speed: null, heading: null },
  } as GeolocationPosition));
  expect(await screen.findByText(/Hors réseau : 1 relevé\(s\) temporaires en mémoire/)).toBeTruthy();
  expect(vi.mocked(request).mock.calls.filter(([path]) => path.endsWith("/positions"))).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Arrêter le partage" }));
  await screen.findByText("Partage arrêté et confirmé par le serveur");
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

it("arrête le partage expiré sans demander la géolocalisation ni conserver de positions", async () => {
  const expired = { ...share, expires_at: new Date(Date.now() - 60_000).toISOString() };
  vi.mocked(request).mockImplementation(async (path) => ({
    data: path === "/me/gps/shares" ? expired : undefined, etag: null,
  }));
  setup();
  await screen.findByRole("button", { name: "Démarrer le partage" });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Démarrer le partage" }));
  await screen.findByText("Partage arrêté et confirmé par le serveur");
  expect(locate).not.toHaveBeenCalled();
  expect(vi.mocked(request).mock.calls.some(([path]) => path.endsWith("/stop"))).toBe(true);
  expect(vi.mocked(request).mock.calls.some(([path]) => path.endsWith("/positions"))).toBe(false);
});
