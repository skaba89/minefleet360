import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { PlatformInvoicesPage } from "./PlatformInvoicesPage";

const { getMock, requestMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  requestMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
  request: requestMock,
}));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ grants: [{ role_code: "PLATFORM_ADMIN", scope_type: "TENANT", site_id: null }] }),
}));
vi.mock("../lib/permissions", () => ({
  can: canMock,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mount(component: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const TENANT_ID = "11111111-1111-4111-8111-111111111111";
const INVOICE_ID = "44444444-4444-4444-8444-444444444444";

const TENANTS = { items: [{ tenant_id: TENANT_ID, code: "mine-a", display_name: "Mine A", status: "ACTIVE", is_demo: true, created_at: "2026-11-05T00:00:00Z", row_version: 1 }] };
const INVOICES = {
  page: 1, page_size: 20, total: 1,
  items: [{
    invoice_id: INVOICE_ID, tenant_id: TENANT_ID, subscription_id: null,
    number: "MF-2026-00001", status: "DRAFT", currency: "GNF", tax_rate_bp: 1800,
    period_start: "2026-11-01", period_end: "2026-11-30",
    subtotal_gnf: 15000000, tax_gnf: 2700000, total_gnf: 17700000, row_version: 1,
  }],
};
const DETAIL = {
  ...INVOICES.items[0],
  issued_at: null, voided_at: null, void_reason: null, notes: null,
  created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z",
  lines: [{
    line_id: "55555555-5555-4555-8555-555555555555",
    description: "Abonnement MineFleet 360 — mensuel", quantity: 1,
    unit_price_gnf: 15000000, amount_gnf: 15000000,
  }],
};

it("affiche l'historique des factures d'une société sélectionnée", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(INVOICES),
  );
  mount(<PlatformInvoicesPage />);
  await screen.findByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  expect(await screen.findByText("MF-2026-00001")).toBeTruthy();
  expect(screen.getByText("Brouillon")).toBeTruthy();
  expect(screen.getByText("17 700 000 GNF")).toBeTruthy();
  await waitFor(() =>
    expect(getMock).toHaveBeenCalledWith(`/platform/tenants/${TENANT_ID}/invoices`, { page: 1, page_size: 20 }),
  );
});

it("détaille une facture au clic sur son numéro", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) => {
    if (path === "/platform/tenants") return Promise.resolve(TENANTS);
    if (path === `/platform/tenants/${TENANT_ID}/invoices`) return Promise.resolve(INVOICES);
    return Promise.resolve(DETAIL);
  });
  mount(<PlatformInvoicesPage />);
  await screen.findByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  fireEvent.click(await screen.findByRole("button", { name: "MF-2026-00001" }));
  expect(await screen.findByText(/Détail de la facture MF-2026-00001/)).toBeTruthy();
  expect(screen.getByText(/Abonnement MineFleet 360 — mensuel/)).toBeTruthy();
  // Le montant apparaît deux fois (prix unitaire et sous-total identiques : quantité 1).
  expect(screen.getAllByText("15 000 000 GNF").length).toBeGreaterThanOrEqual(1);
});

it("crée une facture avec lignes saisies", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) => {
    if (path === "/platform/tenants") return Promise.resolve(TENANTS);
    if (path === `/platform/tenants/${TENANT_ID}/subscriptions`) return Promise.resolve({ items: [] });
    return Promise.resolve(INVOICES);
  });
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformInvoicesPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Créer une facture" }));
  await screen.findAllByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société cliente"), { target: { value: TENANT_ID } });
  fireEvent.change(screen.getByLabelText(/Taxe \(points de base/), { target: { value: "1800" } });
  fireEvent.change(screen.getByLabelText(/Ligne — désignation/), {
    target: { value: "Abonnement MineFleet 360 — mensuel" },
  });
  fireEvent.change(screen.getByLabelText("Quantité"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("Prix unitaire (GNF)"), { target: { value: "15000000" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer la facture" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(`/platform/tenants/${TENANT_ID}/invoices`, {
    method: "POST",
    body: {
      subscription_id: null,
      tax_rate_bp: 1800,
      period_start: null,
      period_end: null,
      lines: [{ description: "Abonnement MineFleet 360 — mensuel", quantity: 1, unit_price_gnf: 15000000 }],
    },
  }));
});

it("émet un brouillon avec If-Match", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(INVOICES),
  );
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformInvoicesPage />);
  await screen.findByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  fireEvent.click(await screen.findByRole("button", { name: "Émettre" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    `/platform/tenants/${TENANT_ID}/invoices/${INVOICE_ID}/issue`,
    { method: "POST", body: {}, ifMatch: '"1"' },
  ));
});

it("annule une facture avec motif obligatoire", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/platform/tenants" ? Promise.resolve(TENANTS) : Promise.resolve(INVOICES),
  );
  requestMock.mockResolvedValue({ data: {}, etag: null });
  mount(<PlatformInvoicesPage />);
  await screen.findByRole("option", { name: /mine-a/ });
  fireEvent.change(screen.getByLabelText("Société"), { target: { value: TENANT_ID } });
  fireEvent.click(await screen.findByRole("button", { name: "Annuler" }));
  fireEvent.change(screen.getByLabelText("Motif d'annulation obligatoire"), {
    target: { value: "Facture émise en double" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
  await waitFor(() => expect(requestMock).toHaveBeenCalledWith(
    `/platform/tenants/${TENANT_ID}/invoices/${INVOICE_ID}/void`,
    { method: "POST", body: { reason: "Facture émise en double" }, ifMatch: '"1"' },
  ));
});

it("refuse la page sans la permission de gestion", () => {
  canMock.mockReturnValue(false);
  mount(<PlatformInvoicesPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(getMock).not.toHaveBeenCalled();
});
