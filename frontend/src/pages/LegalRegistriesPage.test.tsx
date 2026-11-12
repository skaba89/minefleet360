import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { binaryRequest, call, read } from "../api/client";
import { LegalRegistriesPage } from "./LegalRegistriesPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
  binaryRequest: vi.fn(),
}));

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

// --- Cycle documentaire juridique (écart n°1 RECETTE_UI_P0) ------------------------------------------

const adminGrants = [
  { role_code: "TENANT_ADMIN", scope_type: "TENANT", site_id: null },
];
const contract = (extra: object) => ({
  contract_id: "ctr-1", site_id: "s1", reference: "CTR-2026-01", title: "Contrat transport",
  contract_type: "TRANSPORT", counterparty_name: "Transporteur", status: "DRAFT",
  document_sha256: null as string | null, ...extra,
});
const document = (extra: object) => ({
  document_id: "doc-1", original_filename: "justificatif.pdf", sha256: "a".repeat(64),
  byte_size: 2048, status: "PENDING", created_at: "2026-11-12T08:00:00Z", ...extra,
});

it("la création de contrat transmet l'empreinte SHA-256 calculée au client", async () => {
  grants = adminGrants;
  show();
  await screen.findByRole("heading", { name: "Nouveau contrat — brouillon" });
  fireEvent.change(screen.getByLabelText("Référence"), { target: { value: "CTR-2026-02" } });
  fireEvent.change(screen.getByLabelText("Intitulé"), { target: { value: "Contrat transport" } });
  fireEvent.change(screen.getByLabelText("Contrepartie"), { target: { value: "Transporteur" } });
  fireEvent.change(screen.getByLabelText(/Justificatif au format PDF/), {
    target: { files: [new File([new Uint8Array([1, 2, 3])], "justificatif.pdf", { type: "application/pdf" })] },
  });
  await waitFor(() => expect(screen.getByText(/Empreinte SHA-256 du justificatif/)).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
  await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  const body = vi.mocked(call).mock.calls[0][2]?.body as { document_sha256?: string };
  // Empreinte SHA-256 des octets [1, 2, 3] — valeur stable, calculée par le navigateur.
  expect(body.document_sha256).toBe("039058c6f2c0cb492c533b0a4d14ef77cc0f78abccced5287d84a1a2011cfb81");
});

it("le panneau justificatifs affiche les états traduits et la vérification porte sur les PENDING", async () => {
  grants = adminGrants;
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? { items: [contract({})], page: 1, page_size: 25, total: 1 }
      : path === "/legal-contracts/{contract_id}/documents"
      ? [document({}), document({ document_id: "doc-2", status: "VERIFIED" })]
      : emptyPage) as never,
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  expect(await screen.findByText("En attente de vérification")).toBeTruthy();
  expect(screen.getByText("Vérifié")).toBeTruthy();
  const buttons = screen.getAllByRole("button", { name: "Vérifier" });
  expect(buttons).toHaveLength(1);
  fireEvent.click(buttons[0]);
  await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  const [method, template, options] = vi.mocked(call).mock.calls[0];
  expect(method).toBe("post");
  expect(template).toBe("/legal-contracts/{contract_id}/documents/{document_id}/verify");
  expect((options as { path: Record<string, string> }).path).toEqual({ contract_id: "ctr-1", document_id: "doc-1" });
});

it("le dépôt transmet le PDF brut avec le nom de fichier et bloque une empreinte inattendue", async () => {
  grants = adminGrants;
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? { items: [contract({ document_sha256: "f".repeat(64) })], page: 1, page_size: 25, total: 1 }
      : path === "/legal-contracts/{contract_id}/documents"
      ? []
      : emptyPage) as never,
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  const panel = screen.getByRole("region", { name: /Justificatifs du contrat/ });
  const input = (await within(panel).findByLabelText(/Justificatif au format PDF/)) as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File([new Uint8Array([1, 2, 3])], "justificatif.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByText(/ne correspond pas à celle attendue/)).toBeTruthy();
  expect(within(panel).getByRole("button", { name: "Déposer le justificatif" }).hasAttribute("disabled")).toBe(true);
  expect(binaryRequest).not.toHaveBeenCalled();

  // Le même fichier, pour un contrat sans empreinte attendue, part vers l'API avec X-Filename.
  cleanup();
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? { items: [contract({})], page: 1, page_size: 25, total: 1 }
      : path === "/legal-contracts/{contract_id}/documents"
      ? []
      : emptyPage) as never,
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  const secondPanel = screen.getByRole("region", { name: /Justificatifs du contrat/ });
  fireEvent.change(await within(secondPanel).findByLabelText(/Justificatif au format PDF/), {
    target: { files: [new File([new Uint8Array([1, 2, 3])], "contrat-signé.pdf", { type: "application/pdf" })] },
  });
  await waitFor(() => expect(within(secondPanel).getByRole("button", { name: "Déposer le justificatif" }).hasAttribute("disabled")).toBe(false));
  fireEvent.click(within(secondPanel).getByRole("button", { name: "Déposer le justificatif" }));
  await waitFor(() => expect(binaryRequest).toHaveBeenCalledTimes(1));
  const [path, options] = vi.mocked(binaryRequest).mock.calls[0];
  expect(path).toBe("/legal-contracts/ctr-1/documents");
  expect(options).toMatchObject({ method: "POST", contentType: "application/pdf", filename: "contrat-signé.pdf" });
});

it("la soumission exige un justificatif vérifié et une empreinte attendue", async () => {
  grants = adminGrants;
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? { items: [contract({ document_sha256: "a".repeat(64) })], page: 1, page_size: 25, total: 1 }
      : path === "/legal-contracts/{contract_id}/documents"
      ? [document({ status: "VERIFIED" })]
      : emptyPage) as never,
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  await screen.findByText("Vérifié"); // la liste est chargée avant d'évaluer le bouton
  const submit = screen.getByRole("button", { name: "Soumettre pour examen" });
  expect(submit.hasAttribute("disabled")).toBe(false);
  fireEvent.click(submit);
  await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  const [method, template] = vi.mocked(call).mock.calls[0];
  expect(method).toBe("post");
  expect(template).toBe("/legal-contracts/{contract_id}/submit");

  // Sans justificatif vérifié : le bouton est désactivé avant tout appel.
  cleanup();
  vi.mocked(call).mockReset().mockResolvedValue({ data: {}, etag: null } as never);
  vi.mocked(read).mockImplementation(async (path: string) =>
    (path === "/legal-contracts"
      ? { items: [contract({ document_sha256: "a".repeat(64) })], page: 1, page_size: 25, total: 1 }
      : path === "/legal-contracts/{contract_id}/documents"
      ? [document({})]
      : emptyPage) as never,
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Documents" }));
  const blocked = await screen.findByRole("button", { name: "Soumettre pour examen" });
  expect(blocked.hasAttribute("disabled")).toBe(true);
  expect(call).not.toHaveBeenCalled();
});
