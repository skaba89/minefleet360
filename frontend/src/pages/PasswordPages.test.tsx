import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivationPage } from "./PasswordPages";

afterEach(cleanup);

describe("activation par lien d'invitation", () => {
  it("lit le jeton du fragment, le retire de l'URL et l'envoie avec le mot de passe", async () => {
    window.history.replaceState(null, "", "/activation#token=jeton-fictif.123");
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter>
        <ActivationPage />
      </MemoryRouter>,
    );
    expect(window.location.hash).toBe(""); // le jeton ne reste pas dans l'historique
    fireEvent.change(screen.getByLabelText(/Nouveau mot de passe/), { target: { value: "Mot-de-passe-2026" } });
    fireEvent.change(screen.getByLabelText("Confirmer le mot de passe"), { target: { value: "Mot-de-passe-2026" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect((await screen.findByRole("status")).textContent).toContain("Votre compte est activé.");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/auth/invitations/accept");
    expect(JSON.parse(String(init?.body))).toEqual({ token: "jeton-fictif.123", password: "Mot-de-passe-2026" });
  });

  it("refuse l'envoi si les deux mots de passe diffèrent", () => {
    window.history.replaceState(null, "", "/activation#token=jeton-fictif");
    vi.stubGlobal("fetch", vi.fn());
    render(
      <MemoryRouter>
        <ActivationPage />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Nouveau mot de passe/), { target: { value: "Mot-de-passe-2026" } });
    fireEvent.change(screen.getByLabelText("Confirmer le mot de passe"), { target: { value: "Autre-mot-2026" } });
    expect(screen.getByText("Les deux mots de passe sont différents.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Enregistrer" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
