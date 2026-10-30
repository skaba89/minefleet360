import { expect, test } from "@playwright/test";

import { account, apiLogin, uiLogin } from "./fixtures";

// Authentification et autorisation effectives : la disparition d'un menu ne suffit pas
// pour protéger les API métier. Tous les utilisateurs sont issus du seed fictif.
test("le responsable des opérations peut consulter le module carburant", async ({ page, request }) => {
  const manager = account("OPS_MANAGER", "fictif-minier");
  const headers = await apiLogin(request, manager);
  const response = await request.get("/api/v1/fuel/tanks", { headers });
  expect(response.status(), await response.text()).toBe(200);
  const data = await response.json();
  expect(Array.isArray(data.items)).toBeTruthy();

  await uiLogin(page, manager);
  await page.getByRole("navigation", { name: "Navigation principale" })
    .getByRole("link", { name: "Carburant" }).click();
  await expect(page).toHaveURL(/\/carburant$/);
});

test("un utilisateur RH ne peut pas consulter les stocks de carburant", async ({ page, request }) => {
  const hr = account("HR", "fictif-minier");
  const headers = await apiLogin(request, hr);
  const response = await request.get("/api/v1/fuel/tanks", { headers });
  expect(response.status()).toBe(403);

  await uiLogin(page, hr);
  const nav = page.getByRole("navigation", { name: "Navigation principale" });
  await expect(nav.getByRole("link", { name: "Carburant" })).toHaveCount(0);
});
