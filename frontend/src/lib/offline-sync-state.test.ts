import { describe, expect, it } from "vitest";

import { canStartSync, transitionAfterResponse } from "./offline-sync-state";

describe("transitions de synchronisation terrain", () => {
  it("acquitte une opération seulement après réponse HTTP positive", () => {
    expect(transitionAfterResponse(0, 201, 1000)).toEqual({
      state: "synchronized", attempts: 1, retryAt: null, errorCode: null,
    });
  });

  it("garde une opération en attente pendant un délai de reconnexion", () => {
    expect(transitionAfterResponse(1, null, 1000)).toEqual({
      state: "pending", attempts: 2, retryAt: 3000, errorCode: null,
    });
  });

  it("bloque la file si la session expire ou si les droits changent", () => {
    expect(transitionAfterResponse(0, 401, 1000).state).toBe("reauthenticate");
    expect(transitionAfterResponse(0, 403, 1000).state).toBe("rejected");
    expect(transitionAfterResponse(0, 409, 1000).errorCode).toBe("conflict");
    expect(transitionAfterResponse(0, 422, 1000).errorCode).toBe("invalid");
  });

  it("n'autorise la reprise que pour la bonne identité et après le délai", () => {
    expect(canStartSync("pending", 2000, 2000, true, true)).toBe(true);
    expect(canStartSync("pending", 2000, 1999, true, true)).toBe(false);
    expect(canStartSync("pending", null, 2000, false, true)).toBe(false);
    expect(canStartSync("pending", null, 2000, true, false)).toBe(false);
    expect(canStartSync("syncing", null, 2000, true, true)).toBe(false);
    expect(canStartSync("synchronized", null, 2000, true, true)).toBe(false);
    expect(canStartSync("rejected", null, 2000, true, true)).toBe(false);
  });
});
