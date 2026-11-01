import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReconciliationResult } from "./StorageReconciliationPanel";

describe("ReconciliationResult", () => {
  it("shows only aggregate anomaly counts", () => {
    render(<ReconciliationResult result={{ orphan_count: 2, missing_count: 1, consistent: false }} />);
    expect(screen.getByText("Anomalies documentaires à examiner.")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText(/Aucun document n'est supprimé/)).toBeTruthy();
  });

  it("reports a consistent store without pretending to verify documents", () => {
    render(<ReconciliationResult result={{ orphan_count: 0, missing_count: 0, consistent: true }} />);
    expect(screen.getByText("Aucune anomalie détectée.")).toBeTruthy();
  });
});
