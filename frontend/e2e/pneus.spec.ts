import { expect, test } from "@playwright/test";

import { account, apiLogin, uiLogin } from "./fixtures";

/** Pneu suivi de bout en bout : enregistrement, montage, contrôle d'usure, fiche engin, démontage. */
test("cycle d'un pneu depuis l'atelier", async ({ page, request }) => {
  const chief = account("WORKSHOP_CHIEF");
  const headers = await apiLogin(request, chief);
  const listed = await request.get("/api/v1/vehicles", { headers, params: { page_size: 200 } });
  expect(listed.status(), await listed.text()).toBe(200);
  const vehicles = (await listed.json()).items as {
    vehicle_id: string;
    fleet_number: string;
    site_id: string;
    status: string;
  }[];
  const vehicle = vehicles.find((v) => v.status !== "RETIRED");
  expect(vehicle).toBeTruthy();
  const serial = `SN-E2E-${Date.now()}`;

  await uiLogin(page, chief);
  await page.goto("/pneus");
  await page.getByRole("button", { name: "Enregistrer un pneu" }).click();
  const form = page.getByRole("form", { name: "Enregistrer un pneu" });
  await form.getByLabel("Site").selectOption(vehicle!.site_id);
  await form.getByLabel("Marque").fill("MarqueFictive");
  await form.getByLabel("N° de série").fill(serial);
  await form.getByLabel("Modèle").fill("Minier E2E");
  await form.getByLabel("Dimension").fill("27.00R49");
  await form.getByLabel("Sculpture neuve (mm)").fill("80");
  await form.getByLabel("Limite de rebut (mm)").fill("10");
  await form.getByLabel("Coût d'achat (facultatif)").fill("40000000");
  await form.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(serial) })).toBeVisible();

  await page.getByRole("button", { name: "Monter sur un engin" }).click();
  const mount = page.getByRole("form", { name: "Monter le pneu" });
  await mount.getByRole("combobox", { name: "Engin", exact: true }).selectOption(vehicle!.vehicle_id);
  await mount.getByLabel(/Position/).fill("AV-G");
  await mount.getByLabel("Compteur kilométrique de l'engin").fill("12000");
  await mount.getByRole("button", { name: "Monter" }).click();
  await expect(page.getByText("Monté", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Contrôler l'usure" }).click();
  const inspect = page.getByRole("form", { name: "Contrôle d'usure" });
  await inspect.getByLabel("Profondeur de sculpture (mm)").fill("12");
  await inspect.getByLabel("Compteur kilométrique de l'engin").fill("12800");
  await inspect.getByRole("button", { name: "Enregistrer le contrôle" }).click();
  await expect(page.getByText("Sculpture proche de la limite").first()).toBeVisible();
  await expect(page.getByText("800 km / 0 h")).toBeVisible();

  await page.goto(`/vehicules/${vehicle!.vehicle_id}`);
  await expect(page.getByRole("region", { name: "Pneus montés" }).getByText(serial, { exact: false })).toBeVisible();
  await page.getByRole("region", { name: "Pneus montés" }).getByRole("link", { name: new RegExp(serial) }).click();
  await page.getByRole("button", { name: "Démonter" }).click();
  const dismount = page.getByRole("form", { name: "Démonter le pneu" });
  await dismount.getByLabel("Compteur kilométrique de l'engin").fill("13000");
  await dismount.getByRole("button", { name: "Démonter" }).click();
  await expect(page.getByText("En stock", { exact: true })).toBeVisible();
  await expect(page.getByText("1 000 km / 0 h")).toBeVisible();
});
