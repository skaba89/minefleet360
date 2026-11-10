import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { call, read } from "../api/client";
import { PartsPage } from "./PartsPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const page = (items: unknown[]) => ({ items, page: 1, page_size: 25, total: items.length });
const purchaseOrder = {
  purchase_order_id: "po-1", site_id: "s1", replenishment_id: "r-1",
  supplier_name: "Fournisseur Minier SARL", supplier_reference: "PO-2026-001", quantity: "4", status: "DRAFT",
};
const approvedReplenishment = {
  replenishment_id: "r-1", site_id: "s1", spare_part_id: "p-1", spare_part_store_id: "st-1",
  quantity: "4", reference: "REAP-2026-014", status: "APPROVED", created_by: "u2",
  submitted_at: null, decision_by: null, decided_at: null, decision_note: null,
};

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><PartsPage /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  grants = [{ role_code: "STOREKEEPER", scope_type: "TENANT", site_id: null }];
  vi.mocked(read).mockReset().mockImplementation(async (path: string) =>
    (path === "/parts-purchase-orders"
      ? page([purchaseOrder])
      : path === "/part-replenishments"
      ? page([approvedReplenishment])
      : page([])) as never,
  );
  vi.mocked(call).mockReset().mockResolvedValue({ data: {}, etag: null } as never);
});
afterEach(() => { cleanup(); });

it("l'onglet commandes d'achat liste les brouillons avec leur demande liée", async () => {
  show();
  fireEvent.click(screen.getByRole("button", { name: "Commandes d'achat" }));
  expect(await screen.findByText("Fournisseur Minier SARL")).toBeTruthy();
  expect(screen.getByText("PO-2026-001")).toBeTruthy();
  expect((await screen.findAllByText("REAP-2026-014")).length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("Brouillon")).toBeTruthy();
  expect(read).toHaveBeenCalledWith("/parts-purchase-orders", { query: { site_id: "s1", page: 1, page_size: 25 } });
});

it("le magasinier crée une commande depuis une demande approuvée", async () => {
  show();
  fireEvent.click(screen.getByRole("button", { name: "Commandes d'achat" }));
  expect(await screen.findByRole("option", { name: /REAP-2026-014/ })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Demande approuvée"), { target: { value: "r-1" } });
  fireEvent.change(screen.getByLabelText("Fournisseur"), { target: { value: "Fournisseur Minier SARL" } });
  fireEvent.change(screen.getByLabelText("Référence fournisseur"), { target: { value: "PO-2026-002" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer la commande" }));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith("post", "/parts-purchase-orders", {
      body: { replenishment_id: "r-1", supplier_name: "Fournisseur Minier SARL", supplier_reference: "PO-2026-002" },
    }),
  );
  expect((await screen.findAllByText(/Commande enregistrée comme brouillon/)).length).toBeGreaterThanOrEqual(1);
});

it("auditeur : lecture seule des commandes, aucun formulaire de création", async () => {
  grants = [{ role_code: "AUDITOR", scope_type: "TENANT", site_id: null }];
  show();
  fireEvent.click(screen.getByRole("button", { name: "Commandes d'achat" }));
  expect(await screen.findByText("Fournisseur Minier SARL")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Créer la commande" })).toBeNull();
  expect(screen.queryByLabelText("Demande approuvée")).toBeNull();
});

it("sans demande approuvée : la création reste bloquée avec un message explicite", async () => {
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/part-replenishments" ? page([]) : page([])) as never,
  );
  show();
  fireEvent.click(screen.getByRole("button", { name: "Commandes d'achat" }));
  expect(await screen.findByText(/Aucune demande de réapprovisionnement approuvée/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Créer la commande" })).toHaveProperty("disabled", true);
});
