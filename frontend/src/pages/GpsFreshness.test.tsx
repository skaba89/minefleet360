import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FleetPositionsOverview } from "./FleetPositionsOverview";
import { GpsLocationMap } from "./GpsLocationMap";

afterEach(cleanup);

const NOW = Date.parse("2026-10-29T12:00:00Z");
const point = {
  vehicle_id: "camion-fictif",
  latitude: 9.5,
  longitude: -13.7,
  recorded_at: "2026-10-29T10:00:00Z",
  received_at: "2026-10-29T12:00:00Z",
  speed_kmh: 30,
};

describe("présentation des points GPS différés", () => {
  it("annonce un signal ancien sur le point de la vue multi-camions", () => {
    render(<FleetPositionsOverview points={[point]} selectedId={null} onSelect={vi.fn()} now={NOW} />);
    expect(screen.getByRole("button", { name: /Signal ancien ou invalide/ })).toBeTruthy();
  });

  it("actualise le libellé accessible quand le point vieillit", () => {
    const fresh = { ...point, recorded_at: point.received_at };
    const { rerender } = render(
      <FleetPositionsOverview points={[fresh]} selectedId={null} onSelect={vi.fn()} now={NOW} />,
    );
    expect(screen.getByRole("button", { name: /En mouvement/ })).toBeTruthy();
    rerender(<FleetPositionsOverview points={[fresh]} selectedId={null} onSelect={vi.fn()} now={NOW + 120_001} />);
    expect(screen.getByRole("button", { name: /Signal ancien ou invalide/ })).toBeTruthy();
  });

  it("distingue relevé et réception au fuseau du site sans ouvrir la carte externe", () => {
    const { container } = render(<GpsLocationMap point={point} now={NOW} timezone="Africa/Lagos" />);
    expect(screen.getByText(/Signal ancien ou invalide/)).toBeTruthy();
    expect(screen.getByText(/Relevé : 29\/10\/2026 11:00/)).toBeTruthy();
    expect(screen.getByText(/Réception : 29\/10\/2026 13:00/)).toBeTruthy();
    expect(container.querySelector("iframe")).toBeNull();
  });
});
