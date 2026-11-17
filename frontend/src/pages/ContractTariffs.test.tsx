import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { call, read } from "../api/client";
import { ContractTariffsSection } from "./ContractTariffs";

let grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null as string | null }];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const contracts = [{ contract_id: "c1", site_id: "s1", reference: "CT-001", title: "Transport fictif", counterparty_name: "Client fictif" }];
const tariffs = [
  { contract_tariff_id: "t2", contract_id: "c1", basis: "TONNE", unit_price: "27500.0000", currency: "GNF", valid_from: "2026-06-01", note: null, created_at: "2026-06-01T00:00:00Z", current: true },
  { contract_tariff_id: "t1", contract_id: "c1", basis: "TONNE", unit_price: "25000.0000", currency: "GNF", valid_from: "2026-01-01", note: null, created_at: "2026-01-01T00:00:00Z", current: false },
];

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><ContractTariffsSection /></QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockImplementation(((path: string) =>
    Promise.resolve(path === "/contract-tariffs/contracts" ? contracts : tariffs)) as never);
  vi.mocked(call).mockResolvedValue({ data: {}, etag: null } as never);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }];
});

it("liste les versions avec la version en vigueur et la référence du contrat", async () => {
  const client = show();
  const table = await screen.findByRole("table");
  expect(within(table).getAllByText("CT-001 — Client fictif")).toHaveLength(2);
  expect(within(table).getByText("En vigueur")).toBeTruthy();
  expect(within(table).getByText(/27\s500 GNF par tonne mesurée/)).toBeTruthy();
  client.clear();
});

it("saisie d'un tarif : contrat approuvé, mode, prix, devise en majuscules", async () => {
  const client = show();
  await screen.findByRole("table");
  await waitFor(() => expect((screen.getByRole("button", { name: "Saisir un tarif" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Saisir un tarif" }));
  fireEvent.change(screen.getByLabelText("Mode de tarification"), { target: { value: "HOUR" } });
  fireEvent.change(screen.getByLabelText("Prix unitaire"), { target: { value: "350000" } });
  fireEvent.change(screen.getByLabelText("Devise (ISO)"), { target: { value: "gnf" } });
  fireEvent.change(screen.getByLabelText("En vigueur à partir du"), { target: { value: "2026-12-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer le tarif" }));
  await waitFor(() => expect(call).toHaveBeenCalledOnce());
  expect(vi.mocked(call).mock.calls[0]).toEqual([
    "post",
    "/contract-tariffs",
    { body: { contract_id: "c1", basis: "HOUR", unit_price: "350000", currency: "GNF", valid_from: "2026-12-01", note: null } },
  ]);
  client.clear();
});

it("lecture seule sans la permission de gestion des tarifs", async () => {
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
  const client = show();
  await screen.findByRole("table");
  expect(screen.queryByRole("button", { name: "Saisir un tarif" })).toBeNull();
  client.clear();
});
