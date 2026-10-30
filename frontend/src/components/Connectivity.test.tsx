import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConnectivityStatus, OfflineNotice } from "./Connectivity";

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value });
  window.dispatchEvent(new Event(value ? "online" : "offline"));
}

afterEach(() => {
  cleanup();
  setOnline(true);
});

describe("état de la connexion", () => {
  it("annonce le passage hors ligne puis le retour du réseau", () => {
    setOnline(true);
    render(<ConnectivityStatus />);
    expect(screen.getByRole("status").textContent).toContain("Connecté");

    act(() => setOnline(false));
    expect(screen.getByRole("status").textContent).toContain("Hors ligne");

    act(() => setOnline(true));
    expect(screen.getByRole("status").textContent).toContain("Connecté");
  });

  it("explique les limites du premier mode hors ligne", () => {
    setOnline(false);
    render(<OfflineNotice />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("écrans déjà chargés");
    expect(alert.textContent).toContain("enregistrements");
  });
});
