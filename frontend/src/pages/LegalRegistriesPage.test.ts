import { describe, expect, it } from "vitest";

import { authorizedLegalTab } from "./LegalRegistriesPage";

describe("authorizedLegalTab", () => {
  it("opens insurance directly for insurance-only users", () => {
    expect(authorizedLegalTab("contracts", false, true)).toBe("insurance");
  });

  it("opens contracts for contract-only users", () => {
    expect(authorizedLegalTab("insurance", true, false)).toBe("contracts");
  });

  it("preserves the selected registry when both are authorized", () => {
    expect(authorizedLegalTab("insurance", true, true)).toBe("insurance");
    expect(authorizedLegalTab("contracts", true, true)).toBe("contracts");
  });
});
