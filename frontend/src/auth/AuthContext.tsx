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

import { clearOfflineDrafts } from "../lib/offlineDrafts";

type Me = Schemas["MeOut"];

/** Mot de passe correct, second facteur attendu (C-03) : jeton de défi à présenter avec le code. */
export interface MfaChallenge {
  mfaToken: string;
}

interface AuthState {
  status: "loading" | "anonymous" | "authenticated";
  me: Me | null;
  login: (workspaceCode: string, email: string, password: string) => Promise<MfaChallenge | null>;
  verifyMfa: (challenge: MfaChallenge, code: string) => Promise<void>;
  refreshMe: () => Promise<void>;
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

  const enter = useCallback(async (accessToken: string) => {
    setAccessToken(accessToken);
    setMe(await read("/me"));
    setStatus("authenticated");
  }, []);

  const login = useCallback(
    async (workspaceCode: string, email: string, password: string): Promise<MfaChallenge | null> => {
      const { data } = await call("post", "/auth/login", {
        body: { workspace_code: workspaceCode.trim(), email: email.trim(), password },
      });
      if ("mfa_required" in data) return { mfaToken: data.mfa_token };
      await enter(data.access_token);
      return null;
    },
    [enter],
  );

  const verifyMfa = useCallback(
    async (challenge: MfaChallenge, code: string) => {
      const { data } = await call("post", "/auth/mfa/verify", {
        body: { mfa_token: challenge.mfaToken, code: code.trim() },
      });
      await enter(data.access_token);
    },
    [enter],
  );

  const refreshMe = useCallback(async () => {
    setMe(await read("/me"));
  }, []);

  const logout = useCallback(async () => {
    try {
      await request("/auth/logout", { method: "POST" });
    } catch (err) {
      // Révocation non confirmée (réseau coupé…) : le cookie de rafraîchissement resterait valide et la
      // personne suivante sur un poste partagé récupérerait la session. On ne simule pas la déconnexion.
      if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) throw err;
    }
    try {
      if (me) await clearOfflineDrafts(`${me.workspace_code}:${me.user_account_id}`);
    } finally {
      // Révocation confirmée : ne conserver aucune session même si IndexedDB échoue.
      // L'erreur de purge remonte à l'UI, car un brouillon peut subsister sur le poste.
      reset();
    }
  }, [me, reset]);

  const value = useMemo(
    () => ({ status, me, login, verifyMfa, refreshMe, logout }),
    [status, me, login, verifyMfa, refreshMe, logout],
  );
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
