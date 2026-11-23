import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { FleetMap, type MapVehicle } from "./FleetMap";

// jsdom n'a pas de WebGL : MapLibre est simulé ; les marqueurs HTML (vrais boutons) sont rendus dans le conteneur.
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

const truck = (extra: Partial<MapVehicle> = {}): MapVehicle => ({
  id: "v1", label: "CAM-01", latitude: 10.1, longitude: -12.9, state: "moving", stateLabel: "En mouvement",
  speedText: "32.0 km/h", recordedText: "04/11/2026 08:00", ...extra,
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  calls.positions.clear();
  calls.setData.mockReset();
  calls.addProtocol.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("place chaque engin à sa position mesurée, avec un libellé accessible complet", async () => {
  render(<FleetMap vehicles={[truck(), truck({ id: "v2", label: "CAM-02", state: "offline", stateLabel: "Signal ancien ou invalide", speedText: "vitesse inconnue" })]} selectedId={null} onSelect={vi.fn()} />);
  const fresh = await screen.findByRole("button", { name: /CAM-01 · En mouvement · 32.0 km\/h · position mesurée 04\/11\/2026 08:00/ });
  const stale = screen.getByRole("button", { name: /CAM-02 · Signal ancien ou invalide/ });
  expect(fresh.className).toContain("fleet-marker--moving");
  expect(stale.className).toContain("fleet-marker--offline");
  expect(calls.positions.get(fresh)).toEqual([-12.9, 10.1]);
  expect(calls.fitBounds).toHaveBeenCalled();
  // Fond absent : aucun protocole PMTiles enregistré, fond neutre annoncé.
  expect(calls.addProtocol).not.toHaveBeenCalled();
  expect(screen.getByText(/Fond de carte non installé/)).toBeTruthy();
});

it("déplace le marqueur sur la nouvelle mesure et met à jour son état", async () => {
  const { rerender } = render(<FleetMap vehicles={[truck()]} selectedId={null} onSelect={vi.fn()} />);
  const marker = await screen.findByRole("button", { name: /CAM-01/ });
  rerender(<FleetMap vehicles={[truck({ latitude: 10.2, longitude: -12.8, state: "offline", stateLabel: "Signal ancien ou invalide" })]} selectedId={null} onSelect={vi.fn()} />);
  expect(calls.positions.get(marker)).toEqual([-12.8, 10.2]); // animation réduite : saut direct sur la mesure
  expect(marker.getAttribute("aria-label")).toMatch(/Signal ancien ou invalide/);
});

it("ignore une position invalide et retire un engin qui n'est plus transmis", async () => {
  const { rerender } = render(<FleetMap vehicles={[truck(), truck({ id: "bad", label: "BAD", latitude: 120 })]} selectedId={null} onSelect={vi.fn()} />);
  await screen.findByRole("button", { name: /CAM-01/ });
  expect(screen.queryByRole("button", { name: /BAD/ })).toBeNull();
  rerender(<FleetMap vehicles={[]} selectedId={null} onSelect={vi.fn()} />);
  await waitFor(() => expect(screen.queryByRole("button", { name: /CAM-01/ })).toBeNull());
});

it("sélectionne un engin au clic et affiche les zones des sites", async () => {
  const onSelect = vi.fn();
  render(<FleetMap vehicles={[truck()]} geofences={[{ id: "g1", name: "Carrière", coordinates: [[-13, 10], [-12.9, 10], [-12.9, 10.1], [-13, 10]] }]} selectedId={null} onSelect={onSelect} />);
  fireEvent.click(await screen.findByRole("button", { name: /CAM-01/ }));
  expect(onSelect).toHaveBeenCalledWith("v1");
  await waitFor(() => expect(calls.setData).toHaveBeenCalled());
  const data = calls.setData.mock.calls.at(-1)![0] as { features: { properties: { name: string } }[] };
  expect(data.features[0]!.properties.name).toBe("Carrière");
});

it("enregistre le protocole PMTiles quand le fond auto-hébergé est servi", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 200, headers: { "content-type": "application/octet-stream" } })));
  render(<FleetMap vehicles={[truck()]} selectedId={null} onSelect={vi.fn()} />);
  await act(async () => {});
  await screen.findByRole("button", { name: /CAM-01/ });
  expect(screen.queryByText(/Fond de carte non installé/)).toBeNull();
});

it("oriente une flèche selon le cap mesuré, seulement en mouvement et si l'équipement l'envoie", async () => {
  render(<FleetMap vehicles={[
    truck({ headingDeg: 92 }),
    truck({ id: "v2", label: "CAM-02", headingDeg: null }),
    truck({ id: "v3", label: "CAM-03", state: "stopped", stateLabel: "À l'arrêt", headingDeg: 180 }),
  ]} selectedId={null} onSelect={vi.fn()} />);
  const moving = await screen.findByRole("button", { name: /CAM-01 · En mouvement · 32.0 km\/h · cap 92° \(E\)/ });
  expect((moving.querySelector(".fleet-marker-arrow") as HTMLElement).style.transform).toBe("rotate(92deg)");
  for (const name of [/CAM-02/, /CAM-03/]) {
    const marker = screen.getByRole("button", { name });
    expect(marker.querySelector(".fleet-marker-arrow")).toBeNull();
    expect(marker.getAttribute("aria-label")).not.toMatch(/cap/);
  }
});

it("shows the category pictogram for each fleet vehicle without changing its GPS status", async () => {
  render(<FleetMap vehicles={[
    truck({ typeIcon: "dump-truck" }),
    truck({ id: "v2", label: "PEL-01", typeIcon: "excavator", state: "offline", stateLabel: "Signal ancien" }),
  ]} selectedId={null} onSelect={vi.fn()} />);
  const truckMarker = await screen.findByRole("button", { name: /CAM-01/ });
  const excavatorMarker = screen.getByRole("button", { name: /PEL-01/ });
  expect(truckMarker.querySelector(".fleet-marker-type-icon use")?.getAttribute("href")).toBe("/fleet-icons.svg#dump-truck");
  expect(excavatorMarker.querySelector(".fleet-marker-type-icon use")?.getAttribute("href")).toBe("/fleet-icons.svg#excavator");
  expect(excavatorMarker.className).toContain("fleet-marker--offline");
  expect(calls.positions.get(excavatorMarker)).toEqual([-12.9, 10.1]);
});

it("conserve chaque silhouette SVG pendant les nouvelles mesures et changements d'état GPS", async () => {
  const onSelect = vi.fn();
  const { rerender } = render(
    <FleetMap
      vehicles={[
        truck({ typeIcon: "dump-truck", state: "moving" }),
        truck({ id: "exc", label: "PEL-01", typeIcon: "excavator", latitude: 10.3, longitude: -12.7 }),
      ]}
      selectedId="v1"
      onSelect={onSelect}
    />,
  );
  const selected = await screen.findByRole("button", { name: /CAM-01/ });
  const excavator = screen.getByRole("button", { name: /PEL-01/ });
  expect(selected.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#dump-truck");
  expect(excavator.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#excavator");
  expect(selected.className).toContain("fleet-marker--selected");

  rerender(
    <FleetMap
      vehicles={[
        truck({ typeIcon: "dump-truck", latitude: 10.4, longitude: -12.5, state: "offline", stateLabel: "Signal ancien ou invalide" }),
        truck({ id: "exc", label: "PEL-01", typeIcon: "excavator", latitude: 10.5, longitude: -12.6 }),
      ]}
      selectedId="v1"
      onSelect={onSelect}
    />,
  );
  expect(calls.positions.get(selected)).toEqual([-12.5, 10.4]);
  expect(calls.positions.get(excavator)).toEqual([-12.6, 10.5]);
  expect(selected.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#dump-truck");
  expect(excavator.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#excavator");
  expect(selected.className).toContain("fleet-marker--offline");
  expect(selected.className).toContain("fleet-marker--selected");
  fireEvent.click(excavator);
  expect(onSelect).toHaveBeenCalledWith("exc");
});

it("met à jour l'icône quand la catégorie du véhicule change, sans déplacer sa position", async () => {
  const { rerender } = render(
    <FleetMap vehicles={[truck({ typeIcon: "road-truck" })]} selectedId={null} onSelect={vi.fn()} />,
  );
  const marker = await screen.findByRole("button", { name: /CAM-01/ });
  expect(marker.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#road-truck");
  rerender(
    <FleetMap vehicles={[truck({ typeIcon: "tanker" })]} selectedId={null} onSelect={vi.fn()} />,
  );
  expect(marker.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#tanker");
  expect(calls.positions.get(marker)).toEqual([-12.9, 10.1]);
});

it("utilise une silhouette SVG locale de repli si la catégorie n'est pas disponible", async () => {
  render(<FleetMap vehicles={[truck()]} selectedId={null} onSelect={vi.fn()} />);
  const marker = await screen.findByRole("button", { name: /CAM-01/ });
  expect(marker.querySelector("use")?.getAttribute("href")).toBe("/fleet-icons.svg#fleet");
  expect(marker.querySelector(".fleet-marker-type-icon")?.getAttribute("aria-hidden")).toBe("true");
});
