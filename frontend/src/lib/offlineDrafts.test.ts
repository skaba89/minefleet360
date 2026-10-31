import { describe, expect, it } from "vitest";
import { validateOfflineDraft, type OfflineDraft } from "./offlineDrafts";

const draft: OfflineDraft = {
  id: "11111111-1111-4111-8111-111111111111",
  ownerScope: "22222222-2222-4222-8222-222222222222:33333333-3333-4333-8333-333333333333",
  kind: "work_order_note",
  workOrderId: "44444444-4444-4444-8444-444444444444",
  note: "Inspection programmée",
  createdAt: "2026-10-31T09:00:00Z",
};

describe("offline drafts safety boundaries", () => {
  it("accepte uniquement un brouillon de note OT borné", () => {
    expect(() => validateOfflineDraft(draft)).not.toThrow();
  });
  it("refuse un périmètre absent et une note vide", () => {
    expect(() => validateOfflineDraft({ ...draft, ownerScope: "" })).toThrow();
    expect(() => validateOfflineDraft({ ...draft, note: " " })).toThrow();
  });
  it("refuse les charges trop volumineuses et les actions non autorisées", () => {
    expect(() => validateOfflineDraft({ ...draft, note: "x".repeat(1001) })).toThrow();
    expect(() => validateOfflineDraft({ ...draft, kind: "gps_position" as OfflineDraft["kind"] })).toThrow();
  });
  it("refuse les identifiants et horodatages invalides", () => {
    expect(() => validateOfflineDraft({ ...draft, id: "invalid" })).toThrow();
    expect(() => validateOfflineDraft({ ...draft, createdAt: "not-a-date" })).toThrow();
  });
});
