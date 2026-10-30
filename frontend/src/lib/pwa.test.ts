import { afterEach, describe, expect, it, vi } from "vitest";

import { registerOfflineShell } from "./pwa";

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("shell hors ligne", () => {
  it("enregistre le service worker à la racine", async () => {
    const register = vi.fn().mockResolvedValue({ scope: "/" });
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register } });

    await registerOfflineShell();

    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("reste compatible avec un navigateur sans service worker", async () => {
    expect(await registerOfflineShell()).toBeNull();
  });
});
