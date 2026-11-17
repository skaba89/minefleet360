import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { read } from "../api/client";
import { SubcontractorSelect, useSubcontractorName } from "./SubcontractorSelect";

let grants = [{ role_code: "OPS_MANAGER", scope_type: "SITE", site_id: "s1" as string | null }];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", grants }) }));
vi.mock("../api/client", async (original) => ({ ...(await original<typeof import("../api/client")>()), read: vi.fn() }));

const base = { registration_number: null, tax_id: null, country_code: "GN", status_reason: null, notes: null, created_at: "", updated_at: "", row_version: 1 };
const list = [
  { ...base, subcontractor_id: "a", code: "ST-A", legal_name: "Active SARL", status: "ACTIVE" },
  { ...base, subcontractor_id: "s", code: "ST-S", legal_name: "Suspendue SA", status: "SUSPENDED", status_reason: "Assurance" },
  { ...base, subcontractor_id: "e", code: "ST-E", legal_name: "Terminée SA", status: "ENDED", status_reason: "Fin" },
];

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  return client;
}

function Name({ id }: { id: string }) {
  return <span>{useSubcontractorName(id)}</span>;
}

beforeEach(() => vi.mocked(read).mockResolvedValue(list as never));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "OPS_MANAGER", scope_type: "SITE", site_id: "s1" }];
});

it("propose les sous-traitants actifs et conserve le sous-traitant actuel même suspendu", async () => {
  const onChange = vi.fn();
  const client = wrap(<SubcontractorSelect value="s" current="s" onChange={onChange} />);
  expect(await screen.findByRole("option", { name: "ST-A — Active SARL" })).toBeTruthy();
  expect(screen.getByRole("option", { name: "ST-S — Suspendue SA (non actif)" })).toBeTruthy();
  expect(screen.queryByRole("option", { name: /ST-E/ })).toBeNull(); // terminé et non actuel : jamais proposé
  fireEvent.change(screen.getByLabelText("Sous-traitant (référentiel)"), { target: { value: "a" } });
  expect(onChange).toHaveBeenCalledWith("a", "Active SARL");
  client.clear();
});

it("masqué sans droit de lecture du référentiel, sans appel serveur", () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  const client = wrap(<SubcontractorSelect value="" current={null} onChange={vi.fn()} />);
  expect(screen.queryByLabelText("Sous-traitant (référentiel)")).toBeNull();
  expect(read).not.toHaveBeenCalled();
  client.clear();
});

it("affiche le nom du sous-traitant rattaché, ou une mention neutre sans droit de lecture", async () => {
  let client = wrap(<Name id="a" />);
  expect(await screen.findByText("ST-A — Active SARL")).toBeTruthy();
  client.clear();
  cleanup();
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  client = wrap(<Name id="a" />);
  expect(screen.getByText("Rattaché au référentiel")).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(1); // seul le premier rendu (droit de lecture) a interrogé le serveur
  client.clear();
});
