import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { TenantInvoicesPage } from "./TenantInvoicesPage";

const { getMock, canMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  canMock: vi.fn(),
}));

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: getMock,
}));
vi.mock("../auth/AuthContext", () => ({
  useMe: () => ({ grants: [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }] }),
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

const INVOICE_ID = "44444444-4444-4444-8444-444444444444";
const INVOICES = {
  page: 1, page_size: 20, total: 1,
  items: [{
    invoice_id: INVOICE_ID, tenant_id: "99999999-9999-4999-8999-999999999999", subscription_id: null,
    number: "MF-2026-00007", status: "ISSUED", currency: "GNF", tax_rate_bp: 1800,
    period_start: "2026-11-01", period_end: "2026-11-30",
    subtotal_gnf: 15000000, tax_gnf: 2700000, total_gnf: 17700000, row_version: 2,
  }],
};
const DETAIL = {
  ...INVOICES.items[0],
  issued_at: "2026-11-11T10:00:00Z", voided_at: null, void_reason: null, notes: null,
  created_at: "2026-11-11T09:00:00Z", updated_at: "2026-11-11T10:00:00Z",
  lines: [{
    line_id: "55555555-5555-4555-8555-555555555555",
    description: "Abonnement MineFleet 360 — mensuel", quantity: 1,
    unit_price_gnf: 15000000, amount_gnf: 15000000,
  }],
};

it("liste les factures de la société et détaille au clic", async () => {
  canMock.mockReturnValue(true);
  getMock.mockImplementation((path: string) =>
    path === "/tenant/invoices" ? Promise.resolve(INVOICES) : Promise.resolve(DETAIL),
  );
  mount(<TenantInvoicesPage />);
  expect(await screen.findByText("MF-2026-00007")).toBeTruthy();
  expect(screen.getByText("Émise")).toBeTruthy();
  expect(screen.getByText("17 700 000 GNF")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "MF-2026-00007" }));
  expect(await screen.findByText("Sous-total")).toBeTruthy();
  expect(screen.getByText(/2 700 000 GNF \(18 %\)/)).toBeTruthy();
  // Aucune action d'encaissement : la page est en lecture seule.
  expect(screen.queryByRole("button", { name: "Payer" })).toBeNull();
});

it("affiche le message vide sans facture", async () => {
  canMock.mockReturnValue(true);
  getMock.mockResolvedValue({ page: 1, page_size: 20, total: 0, items: [] });
  mount(<TenantInvoicesPage />);
  expect(await screen.findByText("Aucune facture pour votre société.")).toBeTruthy();
});

it("refuse la page sans la permission de lecture", () => {
  canMock.mockReturnValue(false);
  mount(<TenantInvoicesPage />);
  expect(screen.getByRole("alert").textContent).toBe("Vous n'avez pas accès à cette page.");
  expect(getMock).not.toHaveBeenCalled();
});
