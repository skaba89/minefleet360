import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, get, request } from "../api/client";
import { PreventiveCompletionPanel } from "./PreventiveCompletionPanel";

vi.mock("../api/client", async (original) => ({
  ...await original<typeof import("../api/client")>(),
  get: vi.fn(),
  request: vi.fn(),
}));

const order = { work_order_id: "ot-fictif", vehicle_id: "v-fictif", kind: "PREVENTIVE", status: "CLOSED" };
const calendar = {
  maintenance_due_id: "due-fictif", status: "SCHEDULED", plan_code: "ENTRETIEN-30",
  closed_at: "2026-10-29T12:00:00Z", meters: [],
};
const metered = {
  ...calendar,
  meters: [{
    meter_kind: "ODOMETER_KM", frozen_total: null,
    approvals: [{ approval_id: "preuve-km", cumulative_total: "12000.0", approved_at: "2026-10-29T11:00:00Z" }],
  }],
};

function show(allowed = true, current = order) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(<QueryClientProvider client={client}>
    <PreventiveCompletionPanel order={current} allowed={allowed} timeZone="Africa/Conakry" />
  </QueryClientProvider>);
  return { client, invalidate };
}

beforeEach(() => {
  vi.mocked(get).mockReset().mockResolvedValue(calendar);
  vi.mocked(request).mockReset().mockResolvedValue({ data: { status: "COMPLETED", changed: true }, etag: null });
});
afterEach(cleanup);

async function confirmCalendar() {
  await screen.findByText(/Plan calendaire/);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Finaliser l'échéance" }));
}

describe("finalisation préventive en atelier", () => {
  it.each([
    [false, order],
    [true, { ...order, kind: "CORRECTIVE" }],
    [true, { ...order, status: "QUALITY_CHECK" }],
  ])("ne consulte ni n'affiche le dossier hors condition autorisée", (allowed, current) => {
    show(allowed, current);
    expect(get).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Finaliser l'échéance" })).toBeNull();
  });

  it("finalise un plan calendaire avec confirmation et actualise les échéances", async () => {
    const { invalidate } = show();
    await confirmCalendar();
    await screen.findByText("Échéance préventive finalisée.");
    expect(request).toHaveBeenCalledWith("/work-orders/ot-fictif/complete-preventive", { method: "POST", body: {} });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["preventive-dues", "v-fictif"] });
  });

  it("exige un choix explicite et transmet seulement la preuve sélectionnée", async () => {
    vi.mocked(get).mockResolvedValue(metered);
    show();
    const select = await screen.findByRole("combobox");
    const submit = screen.getByRole("button", { name: "Finaliser l'échéance" }) as HTMLButtonElement;
    fireEvent.click(screen.getByRole("checkbox"));
    expect(submit.disabled).toBe(true);
    fireEvent.change(select, { target: { value: "preuve-km" } });
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(submit);
    await waitFor(() => expect(request).toHaveBeenCalledWith(
      "/work-orders/ot-fictif/complete-preventive",
      { method: "POST", body: { odometer_approval_id: "preuve-km" } },
    ));
  });

  it("bloque une preuve requise manquante", async () => {
    vi.mocked(get).mockResolvedValue({ ...calendar, meters: [{ meter_kind: "ODOMETER_KM", frozen_total: null, approvals: [] }] });
    show();
    await screen.findByText(/Aucune approbation utilisable/);
    fireEvent.click(screen.getByRole("checkbox"));
    expect((screen.getByRole("button", { name: "Finaliser l'échéance" }) as HTMLButtonElement).disabled).toBe(true);
    expect(request).not.toHaveBeenCalled();
  });

  it("réutilise une preuve figée même si son total est zéro", async () => {
    vi.mocked(get).mockResolvedValue({ ...calendar, meters: [{ meter_kind: "HOUR_METER", frozen_total: "0.0", approvals: [] }] });
    show();
    await screen.findByText(/preuve déjà figée/);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Finaliser l'échéance" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith(
      "/work-orders/ot-fictif/complete-preventive", { method: "POST", body: {} },
    ));
  });

  it("affiche le rejeu idempotent comme une échéance déjà finalisée", async () => {
    vi.mocked(request).mockResolvedValue({ data: { status: "COMPLETED", changed: false }, etag: null });
    show();
    await confirmCalendar();
    await screen.findByText("Cette échéance était déjà finalisée.");
  });

  it("recharge les preuves après un conflit et redemande confirmation", async () => {
    vi.mocked(request).mockRejectedValue(new ApiError(409, {
      code: "STATE_TRANSITION_INVALID", message_fr: "Preuve périmée", details: null, request_id: null,
    }));
    show();
    await confirmCalendar();
    await screen.findByText(/Le dossier ou les preuves ont changé/);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  });

  it("empêche deux envois pendant la même finalisation", async () => {
    let resolve!: (value: { data: { status: "COMPLETED"; changed: boolean }; etag: null }) => void;
    vi.mocked(request).mockReturnValue(new Promise((done) => { resolve = done; }));
    show();
    await screen.findByText(/Plan calendaire/);
    fireEvent.click(screen.getByRole("checkbox"));
    const form = screen.getByRole("form", { name: "Confirmer la finalisation préventive" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(request).toHaveBeenCalledTimes(1);
    resolve({ data: { status: "COMPLETED", changed: true }, etag: null });
    await screen.findByText("Échéance préventive finalisée.");
  });

  it("une lecture refusée ne laisse pas de formulaire actif", async () => {
    vi.mocked(get).mockRejectedValue(new ApiError(403, {
      code: "PERMISSION_DENIED", message_fr: "Refusé", details: null, request_id: null,
    }));
    show();
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Finaliser l'échéance" })).toBeNull();
  });
});
