import { useState } from "react";

import { ErrorMessage } from "./common";

/** Bouton d'export : un seul envoi à la fois, erreur affichée, avertissement si l'export a été tronqué. */
export function ExportButton({ label = "Exporter (CSV)", run }: { label?: string; run: () => Promise<{ truncated: boolean }> }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [truncated, setTruncated] = useState(false);
  return (
    <span>
      <button
        type="button"
        disabled={pending}
        onClick={() => {
          setPending(true);
          setError(null);
          run()
            .then((r) => setTruncated(r.truncated))
            .catch(setError)
            .finally(() => setPending(false));
        }}
      >
        {pending ? "Export en cours…" : label}
      </button>
      {truncated && <span className="warn-text small"> Export limité aux 5 000 premières lignes : affinez les filtres.</span>}
      {error !== null && <ErrorMessage error={error} />}
    </span>
  );
}
