import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { binaryRequest, call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
import { sha256Hex } from "../lib/hash";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

type Contract = Schemas["ContractOut"];
type Document = Schemas["ContractDocumentOut"];

const STATUS_LABEL: Record<Document["status"], { text: string; tone: "warn" | "ok" }> = {
  PENDING: { text: "En attente de vérification", tone: "warn" },
  VERIFIED: { text: "Vérifié", tone: "ok" },
};
const KIB = 1024;

function sizeInKib(bytes: number): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(bytes / KIB)} Kio`;
}

/**
 * Justificatifs d'un contrat juridique : liste des dépôts avec leurs états (PENDING/VERIFIED),
 * dépôt d'un PDF dont l'empreinte est recalculée au client, vérification (quatre-yeux) et
 * soumission du contrat pour examen. La décision reste une relecture, jamais une signature.
 */
export function ContractDocumentsPanel({ contract, onSubmitted }: { contract: Contract; onSubmitted?: () => void }) {
  const me = useMe();
  const { siteId } = useSites();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fingerprint, setFingerprint] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);
  const canCreate = Boolean(siteId) && can(me.grants, "legal.contract.create", siteId);
  const canReview = can(me.grants, "legal.contract.review", siteId);
  const canSubmit = can(me.grants, "legal.contract.submit", siteId);
  const documents = useQuery({
    queryKey: ["legal-contract-documents", contract.contract_id],
    queryFn: () => read("/legal-contracts/{contract_id}/documents", { path: { contract_id: contract.contract_id } }),
  });
  const draft = contract.status === "DRAFT";
  const expected = contract.document_sha256;
  const mismatch = Boolean(expected && fingerprint && fingerprint !== expected);
  const verified = (documents.data ?? []).some((d) => d.status === "VERIFIED");

  async function pickFile(selected: File | null) {
    setFile(selected);
    setFingerprint("");
    if (!selected) return;
    setFingerprint(await sha256Hex(selected));
  }

  async function deposit() {
    if (!file || saving || mismatch) return;
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await binaryRequest(`/legal-contracts/${contract.contract_id}/documents`, {
        method: "POST",
        body: file,
        contentType: "application/pdf",
        filename: file.name,
      });
      setFile(null);
      setFingerprint("");
      setNotice("Justificatif déposé. Il reste en attente de vérification avant la soumission.");
      await queryClient.invalidateQueries({ queryKey: ["legal-contract-documents", contract.contract_id] });
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  async function verify(documentId: string) {
    if (saving) return;
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await call("post", "/legal-contracts/{contract_id}/documents/{document_id}/verify", {
        path: { contract_id: contract.contract_id, document_id: documentId },
      });
      setNotice("Justificatif relu : les octets du stockage privé ont été revérifiés et rescanés.");
      await queryClient.invalidateQueries({ queryKey: ["legal-contract-documents", contract.contract_id] });
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  async function submitContract() {
    if (saving) return;
    setSaving(true);
    setError(null);
    setNotice("");
    try {
      await call("post", "/legal-contracts/{contract_id}/submit", { path: { contract_id: contract.contract_id } });
      setNotice("Contrat soumis pour examen. La décision reste une relecture, pas une signature électronique.");
      await queryClient.invalidateQueries({ queryKey: ["legal-contract-documents", contract.contract_id] });
      onSubmitted?.();
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label={`Justificatifs du contrat ${contract.reference}`}>
      <h2>Justificatifs — {contract.reference}</h2>
      <p className="muted small">
        Empreinte attendue : <code>{expected ?? "aucune — un contrat sans justificatif ne peut pas être soumis"}</code>
      </p>
      {notice && <p role="status">{notice}</p>}
      <DataState
        loading={documents.isLoading}
        error={documents.error}
        empty={!(documents.data ?? []).length}
        emptyText="Aucun justificatif déposé pour ce contrat."
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Empreinte</th>
              <th scope="col">Taille</th>
              <th scope="col">État</th>
              {canReview && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {(documents.data ?? []).map((document) => (
              <tr key={document.document_id}>
                <td>{document.original_filename}</td>
                <td className="muted small"><code>{document.sha256.slice(0, 16)}…</code></td>
                <td>{sizeInKib(document.byte_size)}</td>
                <td><Badge tone={STATUS_LABEL[document.status].tone}>{STATUS_LABEL[document.status].text}</Badge></td>
                {canReview && (
                  <td>
                    {document.status === "PENDING" && (
                      <button type="button" disabled={saving} onClick={() => void verify(document.document_id)}>
                        Vérifier
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      {canCreate && draft && (
        <form onSubmit={(event) => { event.preventDefault(); void deposit(); }}>
          <h3>Déposer un justificatif</h3>
          <label>Justificatif au format PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => void pickFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {fingerprint && <p className="muted small">Empreinte calculée au client : <code>{fingerprint}</code></p>}
          {mismatch && <p role="alert">L'empreinte du fichier choisi ne correspond pas à celle attendue par le contrat. Le dépôt est bloqué.</p>}
          <button type="submit" disabled={saving || !file || mismatch}>
            {saving ? "Dépôt…" : "Déposer le justificatif"}
          </button>
        </form>
      )}
      {canSubmit && draft && expected && (
        <p>
          <button
            type="button"
            disabled={saving || !verified}
            title={verified ? undefined : "Un justificatif vérifié est requis avant la soumission."}
            onClick={() => void submitContract()}
          >
            {saving ? "Soumission…" : "Soumettre pour examen"}
          </button>
        </p>
      )}
      {error != null && <ErrorMessage error={error} />}
    </section>
  );
}
