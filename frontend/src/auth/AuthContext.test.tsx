import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { onSessionExpired, read, refreshSession, setAccessToken } from "../api/client";
import { purgeDraftsForSignedOutUser } from "../lib/offlineLogout";
import { AuthProvider, useAuth } from "./AuthContext";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {},
  call: vi.fn(),
  onSessionExpired: vi.fn(),
  read: vi.fn(),
  refreshSession: vi.fn(),
  request: vi.fn(),
  setAccessToken: vi.fn(),
}));
vi.mock("../lib/offlineLogout", () => ({ purgeDraftsForSignedOutUser: vi.fn() }));

const profile = {
  workspace_code: "minefleet",
  user_account_id: "33333333-3333-4333-8333-333333333333",
};
let expire: () => void = () => undefined;

function Status() {
  const auth = useAuth();
  return <p>{auth.status}</p>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(refreshSession).mockResolvedValue(true);
  vi.mocked(read).mockResolvedValue(profile as Awaited<ReturnType<typeof read>>);
  vi.mocked(purgeDraftsForSignedOutUser).mockResolvedValue(undefined);
  vi.mocked(onSessionExpired).mockImplementation((handler) => { expire = handler; });
});
afterEach(() => cleanup());

it("retire la session et purge uniquement les brouillons du profil expiré", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><Status /></AuthProvider></QueryClientProvider>);
  await screen.findByText("authenticated");
  act(() => expire());
  await screen.findByText("anonymous");
  expect(setAccessToken).toHaveBeenCalledWith(null);
  await waitFor(() => expect(purgeDraftsForSignedOutUser).toHaveBeenCalledExactlyOnceWith(profile));
});

it("invalide la session même si la purge IndexedDB échoue", async () => {
  vi.mocked(purgeDraftsForSignedOutUser).mockRejectedValue(new Error("IndexedDB indisponible"));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><AuthProvider><Status /></AuthProvider></QueryClientProvider>);
  await screen.findByText("authenticated");
  act(() => expire());
  await screen.findByText("anonymous");
  await waitFor(() => expect(purgeDraftsForSignedOutUser).toHaveBeenCalledOnce());
  expect(setAccessToken).toHaveBeenCalledWith(null);
});
