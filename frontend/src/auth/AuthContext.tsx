import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  ApiError,
  call,
  onSessionExpired,
  read,
  refreshSession,
  request,
  setAccessToken,
  type Schemas,
} from "../api/client";

type Me = Schemas["MeOut"];

interface AuthState {
  status: "loading" | "anonymous" | "authenticated";
  me: Me | null;
  login: (workspaceCode: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [me, setMe] = useState<Me | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  const reset = useCallback(() => {
    setAccessToken(null);
    setMe(null);
    setStatus("anonymous");
    queryClient.clear(); // aucune donnée d'une session ne survit à la suivante
  }, [queryClient]);

  useEffect(() => {
    onSessionExpired(reset);
    let cancelled = false;
    // Restauration de session au chargement : le cookie de rafraîchissement, s'il existe, suffit.
    void (async () => {
      const restored = await refreshSession();
      if (cancelled) return;
      if (!restored) {
        setStatus("anonymous");
        return;
      }
      try {
        const profile = await read("/me");
        if (!cancelled) {
          setMe(profile);
          setStatus("authenticated");
        }
      } catch {
        if (!cancelled) reset();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reset]);

  const login = useCallback(async (workspaceCode: string, email: string, password: string) => {
    const { data } = await call("post", "/auth/login", {
      body: { workspace_code: workspaceCode.trim(), email: email.trim(), password },
    });
    setAccessToken(data.access_token);
    setMe(await read("/me"));
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await request("/auth/logout", { method: "POST" });
    } catch (err) {
      // Révocation non confirmée (réseau coupé…) : le cookie de rafraîchissement resterait valide et la
      // personne suivante sur un poste partagé récupérerait la session. On ne simule pas la déconnexion.
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) throw err;
    }
    reset();
  }, [reset]);

  const value = useMemo(() => ({ status, me, login, logout }), [status, me, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth hors de AuthProvider");
  return ctx;
}

/** Profil de l'utilisateur connecté (à n'utiliser que sous une route protégée). */
export function useMe(): Me {
  const { me } = useAuth();
  if (!me) throw new Error("useMe sans session");
  return me;
}
