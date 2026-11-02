import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { binaryRequest, call, read } from "../api/client";
import { HseInspectionPage, HseInspectionsPage } from "./HseInspectionsPages";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [
  { role_code: "MECHANIC", scope_type: "SITE", site_id: "s1" },
];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({
  useSites: () => ({ siteId: "s1", sites: [{ site_id: "s1", code: "MINE", name: "Mine" }], timezoneOf: () => "Africa/Conakry" }),
}));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
  binaryRequest: vi.fn(),
}));

const template = {
  hse_checklist_template_id: "tpl-1", code: "PRE", version: 2, name: "Prise de poste", target_type: "PRE_SHIFT", active: true,
  created_at: "2026-11-01T08:00:00Z",
  items: [
    { key: "epi", label: "EPI portés", critical: true },
    { key: "radio", label: "Radio testée", critical: false },
  ],
};
const inspection = {
  hse_inspection_id: "ins-1", number: 1, reference: "INS-000001", site_id: "s1", hse_checklist_template_id: "tpl-1",
  template_code: "PRE", template_name: "Prise de poste", template_version: 2, target_type: "PRE_SHIFT", vehicle_id: null,
  vehicle_fleet_number: null, area_note: null, performed_at: "2026-11-02T06:00:00Z", recorded_at: "2026-11-02T06:01:00Z",
  performed_by: "u1", performed_by_name: "Agent fictif", result: "FAIL", nonconformities: 1, critical_nonconformities: 1,
  open_actions: 0, note: null,
  answers: [
    { item_key: "epi", label: "EPI portés", critical: true, result: "NON_COMPLIANT", comment: "Casque absent" },
    { item_key: "radio", label: "Radio testée", critical: false, result: "COMPLIANT", comment: null },
  ],
  evidence: [{ hse_evidence_id: "ev-1", content_type: "image/png", size_bytes: 10, sha256: "a".repeat(64), uploaded_by: "u1", uploaded_at: "2026-11-02T06:02:00Z" }],
  actions: [],
};

function show(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/hse/inspections" element={<HseInspectionsPage />} />
          <Route path="/hse/inspections/:inspectionId" element={<HseInspectionPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(read).mockImplementation((async (path: string) => (path === "/hse/checklist-templates" ? [template] : { items: [], total: 0, page: 1, page_size: 50 })) as never);
  vi.mocked(call).mockImplementation((async (method: string, path: string) =>
    method === "get" && path === "/hse/inspections/{hse_inspection_id}" ? { data: inspection, etag: null } : { data: inspection, etag: null }) as never);
  // Double minimal de Response : seul blob() est utilisé (jsdom ne sait pas convertir un Blob en flux).
  vi.mocked(binaryRequest).mockResolvedValue({
    blob: async () => new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }),
  } as unknown as Response);
  globalThis.URL.createObjectURL = vi.fn(() => "blob:preuve");
  globalThis.URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  grants = [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "s1" }];
});

it("un mécanicien réalise une inspection : constat obligatoire, sans lecture du registre", async () => {
  const client = show("/hse/inspections");
  expect(screen.getByText(/le registre est réservé/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Réaliser une inspection" }));
  const form = screen.getByRole("form", { name: "Réaliser une inspection" });
  await waitFor(() => expect(within(form).getAllByRole("option", { name: /Prise de poste/ }).length).toBe(1));
  fireEvent.change(within(form).getByLabelText("Checklist"), { target: { value: "tpl-1" } });
  fireEvent.change(await within(form).findByLabelText("Résultat : EPI portés"), { target: { value: "NON_COMPLIANT" } });
  fireEvent.change(within(form).getByLabelText("Constat : EPI portés"), { target: { value: "Casque absent" } });
  fireEvent.click(within(form).getByRole("button", { name: "Enregistrer l'inspection" }));
  await waitFor(() => expect(call).toHaveBeenCalledWith("post", "/hse/inspections", expect.anything()));
  const body = (vi.mocked(call).mock.calls.find((c) => c[1] === "/hse/inspections")![2] as { body: { answers: unknown[] } }).body;
  expect(body.answers).toEqual([
    { item_key: "epi", result: "NON_COMPLIANT", comment: "Casque absent" },
    { item_key: "radio", result: "COMPLIANT", comment: null },
  ]);
  expect(await screen.findByText(/INS-000001 enregistrée/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Ouvrir l'inspection" })).toBeNull();
  const file = new File([new Uint8Array([1, 2, 3])], "doc.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText(/Ajouter une photo/), { target: { files: [file] } });
  expect(screen.getByText(/Seules les photos JPEG ou PNG/)).toBeTruthy();
  expect(binaryRequest).not.toHaveBeenCalled();
  client.clear();
});

it("la fiche affiche les réponses figées et charge les photos par l'API authentifiée", async () => {
  grants = [{ role_code: "HSE", scope_type: "TENANT", site_id: null }];
  const client = show("/hse/inspections/ins-1");
  expect(await screen.findByText("Casque absent")).toBeTruthy();
  expect(screen.getByText("Non conforme (critique)")).toBeTruthy();
  await waitFor(() => expect(binaryRequest).toHaveBeenCalledWith("/hse/evidence/ev-1/content"));
  expect(await screen.findByRole("img", { name: "Photo 1 de l'inspection INS-000001" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Ajouter une action corrective" })).toBeTruthy();
  client.clear();
});

it("inspection d'engin non conforme : panne bloquante proposée, jamais automatique", async () => {
  grants = [{ role_code: "MECHANIC", scope_type: "SITE", site_id: "s1" }];
  const vehicleInspection = { ...inspection, target_type: "VEHICLE", vehicle_id: "veh-1", vehicle_fleet_number: "CAM-07" };
  vi.mocked(call).mockImplementation((async (method: string, path: string) =>
    method === "post" && path === "/work-orders"
      ? { data: { work_order_id: "wo-1", reference: "OT-000042" }, etag: null }
      : { data: vehicleInspection, etag: null }) as never);
  const { InspectionBreakdownPrompt } = await import("./HseInspectionsPages");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <InspectionBreakdownPrompt inspection={vehicleInspection as never} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByText(/ne devrait pas être utilisé/)).toBeTruthy();
  expect(call).not.toHaveBeenCalled(); // rien d'automatique
  fireEvent.click(screen.getByRole("button", { name: "Signaler une panne bloquante" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirmer et immobiliser l'engin" }));
  await waitFor(() => expect(call).toHaveBeenCalledWith("post", "/work-orders", expect.anything()));
  const body = (vi.mocked(call).mock.calls[0]![2] as { body: Record<string, unknown> }).body;
  expect(body).toMatchObject({ vehicle_id: "veh-1", priority: "CRITICAL", immobilize: true, symptom_code: "SAFETY_EQUIPMENT" });
  expect(String(body.description)).toContain("INS-000001");
  expect(String(body.description)).toContain("EPI portés");
  expect(String(body.description)).not.toContain("Casque absent"); // constat libre non recopié
  expect(await screen.findByRole("link", { name: "OT-000042" })).toBeTruthy();
  client.clear();
});

it("aucune proposition pour une inspection conforme ou sans engin", async () => {
  const { InspectionBreakdownPrompt } = await import("./HseInspectionsPages");
  const { container } = render(
    <MemoryRouter>
      <InspectionBreakdownPrompt inspection={{ ...inspection, result: "PASS", vehicle_id: "veh-1" } as never} />
      <InspectionBreakdownPrompt inspection={inspection as never} />
    </MemoryRouter>,
  );
  expect(container.innerHTML).toBe("");
});
