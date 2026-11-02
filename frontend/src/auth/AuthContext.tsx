import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  ApiError,
  call,
  lastRefreshFailedOffline,
  onSessionExpired,
  read,
  refreshSession,
  request,
  setAccessToken,
  type Schemas,
} from "../api/client";

import { loadFieldProfile, type FieldProfile } from "../lib/offlineFieldProfile";
import { purgeAfterSessionExpiry, purgeDraftsForSignedOutUser } from "../lib/offlineLogout";

type Me = Schemas["MeOut"];

/** Mot de passe correct, second facteur attendu (C-03) : jeton de défi à présenter avec le code. */
export interface MfaChallenge {
  mfaToken: string;
}

interface AuthState {
  /** offline : démarrage sans réseau avec un profil terrain mémorisé (déclaration HSE seulement). */
  status: "loading" | "anonymous" | "authenticated" | "offline";
  me: Me | null;
  fieldProfile: FieldProfile | null;
  /** Nouvelle tentative de restauration de session (retour du réseau). */
  retrySession: () => Promise<void>;
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
  const [fieldProfile, setFieldProfile] = useState<FieldProfile | null>(null);
  const profileRef = useRef<Me | null>(null);

  const reset = useCallback(() => {
    setAccessToken(null);
    profileRef.current = null;
    setMe(null);
    setStatus("anonymous");
    queryClient.clear(); // aucune donnée d'une session ne survit à la suivante
  }, [queryClient]);

  useEffect(() => {
    onSessionExpired(() => {
      const profile = profileRef.current;
      // Reset immediately; purge best-effort without leaking stale session data into React.
      reset();
      if (profile) void purgeAfterSessionExpiry(profile).catch(() => {
        // Storage may be unavailable: do not claim local data were erased.
      });
    });
    let cancelled = false;
    void restore(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [reset]);

  // Restauration de session : le cookie de rafraîchissement, s'il existe, suffit. Sans réseau, un profil
  // terrain mémorisé ouvre le mode hors ligne restreint ; il ne vaut jamais session serveur.
  async function restore(isCancelled: () => boolean = () => false): Promise<void> {
    const restored = await refreshSession();
    if (isCancelled()) return;
    if (!restored) {
      const profile = lastRefreshFailedOffline() ? loadFieldProfile() : null;
      setFieldProfile(profile);
      setStatus(profile ? "offline" : "anonymous");
      return;
    }
    try {
      const profile = await read("/me");
      if (!isCancelled()) {
        profileRef.current = profile;
        setMe(profile);
        setFieldProfile(null);
        setStatus("authenticated");
      }
    } catch {
      if (!isCancelled()) reset();
    }
  }

  const retrySession = useCallback(() => restore(), []);

  useEffect(() => {
    if (status !== "offline") return;
    const retry = () => void restore();
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [status]);

  const enter = useCallback(async (accessToken: string) => {
    setAccessToken(accessToken);
    const profile = await read("/me");
    profileRef.current = profile;
    setMe(profile);
    setStatus("authenticated");
  }, []);

  const login = useCallback(
    async (workspaceCode: string, email: string, password: string): Promise<MfaChallenge | null> => {
      const workspace = workspaceCode.trim().toLowerCase();
      const { data } =
        workspace === "mf-platform"
          ? await call("post", "/auth/platform/login", {
              body: { email: email.trim(), password },
            })
          : await call("post", "/auth/login", {
              body: { workspace_code: workspace, email: email.trim(), password },
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
    const profile = await read("/me");
    profileRef.current = profile;
    setMe(profile);
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
      if (me) await purgeDraftsForSignedOutUser(me);
    } finally {
      // Révocation confirmée : ne conserver aucune session même si IndexedDB échoue.
      // L'erreur de purge remonte à l'UI, car un brouillon peut subsister sur le poste.
      reset();
    }
  }, [me, reset]);

  const value = useMemo(
    () => ({ status, me, fieldProfile, retrySession, login, verifyMfa, refreshMe, logout }),
    [status, me, fieldProfile, retrySession, login, verifyMfa, refreshMe, logout],
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
