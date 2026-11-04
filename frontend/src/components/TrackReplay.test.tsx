import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { TrackReplay, type ReplayTrack } from "./TrackReplay";

const calls = vi.hoisted(() => ({ setData: vi.fn(), fitBounds: vi.fn(), easeTo: vi.fn(), addProtocol: vi.fn(), positions: new Map<HTMLElement, [number, number]>() }));
vi.mock("maplibre-gl", () => {
  class FakeMap {
    container: HTMLElement;
    constructor(options: { container: HTMLElement }) {
      this.container = options.container;
    }
    addControl() {}
    on(event: string, cb: () => void) {
      if (event === "load") setTimeout(cb, 0);
    }
    addSource() {}
    addLayer() {}
    getSource() {
      return { setData: calls.setData };
    }
    fitBounds(...args: unknown[]) {
      calls.fitBounds(...args);
    }
    easeTo(...args: unknown[]) {
      calls.easeTo(...args);
    }
    getZoom() {
      return 6;
    }
    remove() {}
  }
  class FakeMarker {
    element: HTMLElement;
    lngLat = { lng: 0, lat: 0 };
    constructor(options: { element: HTMLElement }) {
      this.element = options.element;
    }
    setLngLat(value: [number, number]) {
      this.lngLat = { lng: value[0], lat: value[1] };
      calls.positions.set(this.element, value);
      return this;
    }
    getLngLat() {
      return this.lngLat;
    }
    addTo(map: FakeMap) {
      map.container.appendChild(this.element);
      return this;
    }
    remove() {
      this.element.remove();
    }
  }
  class LngLatBounds {
    extend() {
      return this;
    }
  }
  const api = { Map: FakeMap, Marker: FakeMarker, LngLatBounds, NavigationControl: class {}, addProtocol: calls.addProtocol, setWorkerUrl: vi.fn() };
  return api;
});

const iso = (minute: number) => new Date(Date.UTC(2026, 10, 4, 7, minute)).toISOString();
const track: ReplayTrack = {
  points: [
    { latitude: 10, longitude: -12, recorded_at: iso(0), speed_kmh: 30, heading_deg: 90 },
    { latitude: 10, longitude: -11.99, recorded_at: iso(1), speed_kmh: 32, heading_deg: 91 },
    { latitude: 10, longitude: -11.98, recorded_at: iso(2), speed_kmh: 0, heading_deg: null },
    { latitude: 10.05, longitude: -11.9, recorded_at: iso(40), speed_kmh: 20, heading_deg: null },
  ],
  gaps: [{ start: iso(2), end: iso(40) }],
  stops: [{ start: iso(2), end: iso(10), minutes: 8, latitude: 10, longitude: -11.98 }],
};

function marker(): HTMLElement {
  return document.querySelector(".replay-marker") as HTMLElement;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  calls.setData.mockReset();
  calls.positions.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("place le marqueur sur la première mesure et trace le trajet coupé à l'interruption", async () => {
  render(<TrackReplay track={track} timezone="Africa/Conakry" />);
  expect(await screen.findByText("Position mesurée")).toBeTruthy();
  await waitFor(() => expect(calls.positions.get(marker())).toEqual([-12, 10]));
  expect(marker().className).toContain("replay-marker--measured");
  expect(screen.getByText(/30.0 km\/h · cap 90° \(E\)/)).toBeTruthy();
  const traced = calls.setData.mock.calls.map((c) => c[0] as { geometry?: { coordinates: unknown[] } });
  // Le tracé complet ne relie pas les deux côtés de l'interruption : un seul tronçon de 3 mesures.
  expect(traced.some((d) => JSON.stringify(d.geometry?.coordinates) === JSON.stringify([[[-12, 10], [-11.99, 10], [-11.98, 10]]]))).toBe(true);
  expect(calls.fitBounds).toHaveBeenCalled();
});

it("le curseur saute sur l'instant choisi et signale l'interruption du signal", async () => {
  render(<TrackReplay track={track} timezone="Africa/Conakry" />);
  await screen.findByText("Position mesurée");
  await waitFor(() => expect(calls.positions.get(marker())).toEqual([-12, 10])); // carte chargée
  const slider = screen.getByRole("slider");
  fireEvent.change(slider, { target: { value: "500" } }); // 20 min : pendant le trou de signal
  expect(screen.getByText(/Signal interrompu/)).toBeTruthy();
  expect(calls.positions.get(marker())).toEqual([-11.98, 10]);
  expect(marker().className).toContain("replay-marker--gap");
  fireEvent.change(slider, { target: { value: "1000" } });
  expect(calls.positions.get(marker())).toEqual([-11.9, 10.05]);
});

it("lecture : interpolation signalée comme non mesurée, puis fin et relecture", async () => {
  let now = 0;
  vi.stubGlobal("performance", { now: () => now });
  const frames: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => frames.push(cb));
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  render(<TrackReplay track={track} timezone="Africa/Conakry" />);
  await screen.findByText("Position mesurée");
  await waitFor(() => expect(calls.positions.get(marker())).toEqual([-12, 10])); // carte chargée
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "60" } });
  fireEvent.click(screen.getByRole("button", { name: "Lecture" }));
  await act(async () => {
    now = 500; // 0,5 s réelle × 60 = 30 s de trajet : entre les deux premières mesures
    frames.shift()?.(now);
  });
  expect(screen.getByText(/Entre deux mesures : position estimée pour l'animation, non mesurée/)).toBeTruthy();
  expect(marker().className).toContain("replay-marker--interpolated");
  expect(screen.getByText(/dernière mesure 04\/11\/2026 07:00/)).toBeTruthy();
  await act(async () => {
    now = 1_000_000;
    frames.shift()?.(now);
  });
  expect(await screen.findByRole("button", { name: "Rejouer" })).toBeTruthy();
});

it("annonce qu'il n'y a rien à relire avec moins de deux mesures", () => {
  render(<TrackReplay track={{ ...track, points: track.points.slice(0, 1) }} timezone="Africa/Conakry" />);
  expect(screen.getByText(/rien à relire/)).toBeTruthy();
});
