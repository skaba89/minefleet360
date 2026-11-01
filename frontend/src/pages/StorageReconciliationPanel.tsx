import { useState } from "react";

import { read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";

type Summary = Schemas["ReconciliationSummaryOut"];

/** Pure projection: no private object keys, filenames or contract identities. */
export function ReconciliationResult({ result }: { result: Summary }) {
  return (
    <div role="status">
      <p>{result.consistent ? "Aucune anomalie détectée." : "Anomalies documentaires à examiner."}</p>
      <p>Fichiers orphelins : <strong>{result.orphan_count}</strong></p>
      <p>Fichiers manquants : <strong>{result.missing_count}</strong></p>
      <p className="muted">Contrôle en lecture seule. Aucun document n'est supprimé ou validé automatiquement.</p>
    </div>
  );
}

export function StorageReconciliationPanel() {
  const { grants } = useMe();
  const tenantReviewer = grants.some(
    (grant) => grant.scope_type === "TENANT" && can([grant], "legal.contract.review"),
  );
  const [result, setResult] = useState<Summary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  if (!tenantReviewer) return null;

  async function run() {
    if (running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const report = await read("/legal-contracts/storage-reconciliation");
      setResult(report);
    } catch (caught) {
      setError(caught);
    } finally {
      setRunning(false);
    }
  }

  return (
    <section aria-label="Contrôle du stockage documentaire">
      <h2>Intégrité des documents</h2>
      <p className="muted">Compare les références PostgreSQL aux fichiers privés S3/MinIO de votre entreprise. Aucun nom de fichier n'est affiché.</p>
      <button type="button" disabled={running} onClick={() => void run()}>
        {running ? "Contrôle en cours…" : "Contrôler le stockage"}
      </button>
      {error !== null && <ErrorMessage error={error} />}
      {result !== null && <ReconciliationResult result={result} />}
    </section>
  );
}
