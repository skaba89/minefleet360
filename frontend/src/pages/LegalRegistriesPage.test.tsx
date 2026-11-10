import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { call, read } from "../api/client";
import { LegalRegistriesPage } from "./LegalRegistriesPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn(), call: vi.fn() }));

const policy = (id: string, extra: object) => ({
  insurance_policy_id: id, site_id: "s1", policy_number: `POL-${id}`, insurer_name: "Assurance Minière SA",
  coverage_type: "FLEET", coverage_start: "2026-01-01", coverage_end: "2026-12-31",
  premium_amount: null, currency: "GNF", contract_id: null, ...extra,
});
const emptyPage = { items: [], page: 1, page_size: 25, total: 0 };

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}><MemoryRouter><LegalRegistriesPage /></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  grants = [{ role_code: "FINANCE", scope_type: "TENANT", site_id: null }];
  vi.mocked(read).mockReset().mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? emptyPage
      : path === "/insurance-policies"
      ? { items: [policy("1", {})], page: 1, page_size: 25, total: 1 }
      : path === "/insurance-policies/expiring"
      ? [policy("1", { coverage_end: "2026-10-30", validity: "EXPIRED" }), policy("2", { validity: "EXPIRING" })]
      : emptyPage) as never,
  );
  vi.mocked(call).mockReset().mockResolvedValue({ data: {}, etag: null } as never);
});
afterEach(() => { cleanup(); });

it("l'onglet assurances affiche les échéances avec leur état traduit", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Assurances" }));
  expect(await screen.findByText("POL-2")).toBeTruthy();
  expect(screen.getByText("Expirée")).toBeTruthy();
  expect(screen.getByText("Échéance proche")).toBeTruthy();
  expect(read).toHaveBeenCalledWith("/insurance-policies/expiring", { query: { within_days: 45, site_id: "s1" } });
  expect(screen.getByRole("heading", { name: "Échéances d'assurance — horizon 45 jours" })).toBeTruthy();
});

it("l'onglet assurances liste aussi les polices enregistrées", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Assurances" }));
  expect(screen.getByRole("heading", { name: "Polices enregistrées" })).toBeTruthy();
  expect((await screen.findAllByText("POL-1")).length).toBeGreaterThanOrEqual(1);
});

it("auditeur : échéances en lecture seule, aucun formulaire de création", async () => {
  grants = [{ role_code: "AUDITOR", scope_type: "TENANT", site_id: null }];
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Assurances" }));
  expect(await screen.findByText("POL-2")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Enregistrer la police" })).toBeNull();
  expect(screen.queryByLabelText("Numéro de police")).toBeNull();
});
