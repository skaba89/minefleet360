import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { ISSUES, label } from "../lib/labels";

/** États standard d'une zone de données : chargement, erreur (dont 403/404), vide. */
export function DataState({
  loading,
  error,
  empty,
  emptyText = "Aucun élément à afficher.",
  children,
}: {
  loading: boolean;
  error: unknown;
  empty: boolean;
  emptyText?: string;
  children: ReactNode;
}) {
  if (loading) return <p className="muted" role="status">Chargement…</p>;
  if (error) return <ErrorMessage error={error} />;
  if (empty) return <p className="muted">{emptyText}</p>;
  return <>{children}</>;
}

function reasonsOf(error: ApiError): { code: string; date?: string | null }[] {
  const details = error.details as { reasons?: { code: string; date?: string | null }[] } | null;
  return details?.reasons ?? [];
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return <p className="error" role="alert">Erreur inattendue.</p>;
  const title =
    error.status === 403
      ? "Vous n'avez pas accès à cette information."
      : error.status === 404
        ? "Élément introuvable ou hors de votre périmètre."
        : error.message;
  const reasons = reasonsOf(error);
  return (
    <div className="error" role="alert">
      <p>{title}</p>
      {reasons.length > 0 && (
        <ul>
          {reasons.map((r) => (
            <li key={r.code}>
              {label(ISSUES, r.code)}
              {r.date ? ` (échéance ${r.date.split("-").reverse().join("/")})` : ""}
            </li>
          ))}
        </ul>
      )}
      {error.requestId && <p className="muted small">Référence : {error.requestId}</p>}
    </div>
  );
}

export function Badge({ tone, children }: { tone: "ok" | "warn" | "bad" | "neutral"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pager" aria-label="Pagination">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Précédent
      </button>
      <span>
        Page {page} sur {pages} — {total} élément{total > 1 ? "s" : ""}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Suivant
      </button>
    </nav>
  );
}
