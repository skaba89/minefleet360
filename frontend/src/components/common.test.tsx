import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { AccessDenied } from "./common";

afterEach(() => cleanup());

// Forme canonique unique du refus d'accès direct (écart n°2 de la recette UI P0) :
// même texte, même sémantique (role="alert") et même style (div.error) sur toutes les pages.
it("rend le refus canonique avec le texte, le rôle et le style uniformisés", () => {
  render(<AccessDenied />);
  const alert = screen.getByRole("alert");
  expect(alert.tagName).toBe("DIV");
  expect(alert.className).toBe("error");
  expect(alert.textContent).toBe("Vous n'avez pas accès à cette page.");
});
