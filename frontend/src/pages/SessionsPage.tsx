import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState } from "../components/common";
import { formatDateTime } from "../lib/time";

type SessionRow = Schemas["SessionOut"];

/** Libellé lisible du navigateur à partir du user-agent (les serveurs n'interprètent pas davantage). */
function browserLabel(userAgent: string | null): string {
  if (!userAgent) return "Appareil inconnu";
  if (userAgent.includes("Edg/")) return "Edge";
  if (userAgent.includes("OPR/") || userAgent.includes("Opera")) return "Opera";
  if (userAgent.includes("Firefox")) return "Firefox";
  if (userAgent.includes("Chrome") || userAgent.includes("Chromium")) return "Chrome";
  if (userAgent.includes("Safari")) return "Safari";
  return userAgent.slice(0, 40);
}

export function SessionsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessions = useQuery({ queryKey: ["me-sessions"], queryFn: () => read("/me/sessions") });
  const rows = sessions.data ?? [];

  const refresh = async (message: string) => {
    setError(null);
    setNotice(message);
    await queryClient.invalidateQueries({ queryKey: ["me-sessions"] });
  };

  const revokeOne = async (session: SessionRow) => {
    try {
      await call("post", "/me/sessions/{session_id}/revoke", { path: { session_id: session.auth_session_id } });
      if (session.is_current) {
        // Session courante fermée : la requête suivante entraînera la reconnexion (comportement voulu).
        await refresh("Session courante fermée : vous serez déconnecté à la prochaine action.");
      } else {
        await refresh("Session fermée.");
      }
    } catch {
      setError("Impossible de fermer cette session (déjà fermée ou erreur réseau). Rechargez la liste.");
    }
  };

  const revokeOthers = async () => {
    try {
      const { data } = await call("post", "/me/sessions/revoke-others");
      await refresh(`${data.revoked} autre(s) session(s) fermée(s). Seule la session courante reste active.`);
    } catch {
      setError("Impossible de fermer les autres sessions. Rechargez la liste et réessayez.");
    }
  };

  return (
    <section>
      <h1>Mes sessions</h1>
      <p className="muted">
        Chaque connexion ouvre une session sur un appareil. Fermez celles que vous ne reconnaissez pas, puis
        changez votre mot de passe depuis <strong>Sécurité</strong>.
      </p>
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <DataState loading={sessions.isLoading} error={sessions.error} empty={rows.length === 0}>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">Sessions actives de votre compte</caption>
            <thead>
              <tr>
                <th scope="col">Appareil</th>
                <th scope="col">Adresse IP</th>
                <th scope="col">Dernière activité</th>
                <th scope="col">Ouverte le</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.auth_session_id}>
                  <td>
                    {browserLabel(s.user_agent)}{" "}
                    {s.is_current && <strong>(session courante)</strong>}
                  </td>
                  <td>{s.ip_address ?? "—"}</td>
                  <td>{formatDateTime(s.last_seen_at, me.timezone)}</td>
                  <td>{formatDateTime(s.created_at, me.timezone)}</td>
                  <td>
                    <button type="button" onClick={() => void revokeOne(s)}>
                      Fermer
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 1 && (
          <div className="toolbar">
            <button type="button" onClick={() => void revokeOthers()}>
              Fermer toutes les autres sessions
            </button>
          </div>
        )}
      </DataState>
    </section>
  );
}
