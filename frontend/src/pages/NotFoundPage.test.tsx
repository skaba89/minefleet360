import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import { NotFoundPage } from "./NotFoundPage";

afterEach(cleanup);

describe("page introuvable (404)", () => {
  it("explique l'erreur et propose un retour à l'accueil", () => {
    render(
      <MemoryRouter initialEntries={["/route-inexistante"]}>
        <NotFoundPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Page introuvable" })).toBeTruthy();
    const retour = screen.getByRole("link", { name: "Retour à l'accueil" });
    expect(retour.getAttribute("href")).toBe("/");
  });

  it("ne s'affiche pas comme un contenu métier (texte court, sans données)", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/route-inexistante"]}>
        <NotFoundPage />
      </MemoryRouter>,
    );
    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.querySelectorAll("form")).toHaveLength(0);
  });
});
