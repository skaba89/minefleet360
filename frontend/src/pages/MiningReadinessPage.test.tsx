import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ApiError, call, read } from "../api/client";
import { MiningReadinessPage } from "./MiningReadinessPage";

let grants: { role_code: string; scope_type: string; site_id: string | null }[] = [];
vi.mock("../auth/AuthContext", () => ({ useMe: () => ({ user_account_id: "u1", timezone: "Africa/Conakry", grants }) }));
vi.mock("../site/SiteContext", () => ({ useSites: () => ({ siteId: "s1", timezoneOf: () => "Africa/Conakry" }) }));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  read: vi.fn(),
  call: vi.fn(),
}));

const revision = {
  revision_id: "rev-1",
  version: 2,
  provenance: "Levé topo 2026-11",
  created_at: "2026-11-20T08:00:00Z",
  report_count: 1,
};
const report = {
  report_id: "rep-1",
  digest_version: "mining-readiness-v1",
  evidence_digest: "a".repeat(64),
  tolerance_m: 2,
  actor_user_id: "u9",
  created_at: "2026-11-21T09:30:00Z",
  finding_count: 1,
  tolerance_qualification_id: "qual-1",
  evidence_kind: "HISTORICAL_TECHNICAL_INSPECTION",
};
const detail = { summary: report, findings: [{ code: "MISSING_RESTRICTION", segment_id: "seg-1" }] };
const review = {
  report_id: "rep-1",
  digest_version: "mining-readiness-v1",
  evidence_digest: "a".repeat(64),
  decisions: [
    {
      decision_id: "dec-1",
      report_id: "rep-1",
      stage: "TECHNICAL",
      decision: "APPROVED",
      actor_user_id: "u8",
      reason: "Réseau conforme au levé",
      created_at: "2026-11-21T10:00:00Z",
      evidence_kind: "MINING_REVIEW_DECISION",
    },
  ],
  evidence_kind: "MINING_REVIEW_HISTORY",
};

const REPORTS = "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports";

function mockRead() {
  vi.mocked(read).mockReset().mockImplementation(async (path: string) => {
    if (path === "/sites/{site_id}/mining/revisions") return [revision] as never;
    if (path === `${REPORTS}/{report_id}/review`) return review as never;
    if (path === `${REPORTS}/{report_id}`) return detail as never;
    if (path === REPORTS) return { items: [report], next_cursor: null } as never;
    throw new Error(`chemin inattendu : ${path}`);
  });
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MiningReadinessPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  grants = [{ role_code: "OPS_MANAGER", scope_type: "TENANT", site_id: null }];
  mockRead();
  vi.mocked(call).mockReset().mockResolvedValue({ data: {}, etag: null } as never);
});
afterEach(() => {
  cleanup();
});

it("liste les relevés d'un levé et détaille preuves, anomalies et historique", async () => {
  show();
  expect(await screen.findByText(/Version 2/)).toBeTruthy();
  expect(await screen.findByText("2.00 m")).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Examiner" }));
  expect(await screen.findByText("a".repeat(64))).toBeTruthy();
  expect(screen.getByText("MISSING_RESTRICTION")).toBeTruthy();
  expect(screen.getByText("Réseau conforme au levé")).toBeTruthy();
  expect(screen.getByText("Étape technique")).toBeTruthy();
  expect(read).toHaveBeenCalledWith("/sites/{site_id}/mining/revisions", { path: { site_id: "s1" } });
  expect(read).toHaveBeenCalledWith(REPORTS, {
    path: { site_id: "s1", revision_id: "rev-1" },
    query: { limit: 50 },
  });
});

it("propose les décisions aux détenteurs de la permission et soumet un rejet motivé", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Examiner" }));
  fireEvent.click(await screen.findByRole("button", { name: "Rejeter ce relevé" }));
  expect(await screen.findByText(/Rejeter le relevé du/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/Motif/), { target: { value: "Le relevé est antérieur au dernier levé." } });
  fireEvent.click(screen.getByRole("button", { name: "Rejeter" }));
  await waitFor(() =>
    expect(call).toHaveBeenCalledWith(
      "post",
      `${REPORTS}/{report_id}/reject`,
      expect.objectContaining({
        path: { site_id: "s1", revision_id: "rev-1", report_id: "rep-1" },
        body: { stage: "TECHNICAL", reason: "Le relevé est antérieur au dernier levé." },
      }),
    ),
  );
});

it("ne propose aucune décision sans la permission correspondante", async () => {
  grants = [{ role_code: "DISPATCHER", scope_type: "SITE", site_id: "s1" }];
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Examiner" }));
  await waitFor(() => expect(screen.getByText("MISSING_RESTRICTION")).toBeTruthy());
  expect(screen.queryByRole("button", { name: "Rejeter ce relevé" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Approuver ce relevé" })).toBeNull();
});

it("signale l'erreur du serveur quand la décision est refusée", async () => {
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Examiner" }));
  fireEvent.click(await screen.findByRole("button", { name: "Approuver ce relevé" }));
  vi.mocked(call).mockRejectedValueOnce(
    new ApiError(422, {
      code: "SELF_APPROVAL_FORBIDDEN",
      message_fr: "Cette action doit être validée par une autre personne que son auteur.",
      details: null,
      request_id: null,
    }),
  );
  fireEvent.change(screen.getByLabelText(/Motif/), { target: { value: "Je valide mon propre relevé." } });
  fireEvent.click(screen.getByRole("button", { name: "Approuver" }));
  expect(await screen.findByText(/autre personne que son auteur/)).toBeTruthy();
});
