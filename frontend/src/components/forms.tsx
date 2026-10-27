import { useState, type FormEvent, type ReactNode } from "react";

import { ErrorMessage } from "./common";

/** Chaîne vide d'un champ facultatif → null (l'API distingue « absent » et « vide »). */
export function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function intOrNull(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

export function Options({ map, empty }: { map: Record<string, string>; empty?: string }) {
  return (
    <>
      {empty !== undefined && <option value="">{empty}</option>}
      {Object.entries(map).map(([code, text]) => (
        <option key={code} value={code}>
          {text}
        </option>
      ))}
    </>
  );
}

/**
 * Formulaire d'action : envoi unique (bouton désactivé pendant l'envoi, pas de double soumission),
 * erreur serveur affichée en français, fermeture ou message de succès à la fin.
 */
export function ActionForm({
  title,
  submitLabel,
  onSubmit,
  onDone,
  onCancel,
  children,
  danger = false,
}: {
  title: string;
  submitLabel: string;
  onSubmit: () => Promise<unknown>;
  onDone?: () => void;
  onCancel?: () => void;
  children: ReactNode;
  danger?: boolean;
}) {
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await onSubmit();
      onDone?.();
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="card form-grid" onSubmit={(e) => void submit(e)} aria-label={title}>
      <h2>{title}</h2>
      {children}
      {error !== null && <ErrorMessage error={error} />}
      <div className="row">
        <button type="submit" className={danger ? "danger" : "primary"} disabled={pending}>
          {pending ? "Enregistrement…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Annuler
          </button>
        )}
      </div>
    </form>
  );
}

/** Ligne libellé / valeur d'une fiche. */
export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children ?? "—"}</dd>
    </div>
  );
}
