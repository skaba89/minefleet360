import { useEffect, useState } from "react";

import { binaryRequest } from "../api/client";
import { ErrorMessage } from "./common";

/** Envoi de photos (JPEG ou PNG, 2 Mo maximum), analysées par antivirus avant stockage privé. */
export function EvidenceUploader({ uploadPath, onUploaded }: { uploadPath: string; onUploaded: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  return (
    <div>
      <label>
        Ajouter une photo (JPEG ou PNG, 2 Mo max.)
        <input
          type="file"
          accept="image/jpeg,image/png"
          capture="environment"
          disabled={pending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            setError(null);
            setMessage(null);
            if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 2_000_000) {
              setMessage("Seules les photos JPEG ou PNG de 2 Mo au plus sont acceptées.");
              return;
            }
            setPending(true);
            binaryRequest(uploadPath, { method: "POST", body: file, contentType: file.type })
              .then(() => {
                setMessage("Photo enregistrée après analyse antivirus.");
                onUploaded();
              })
              .catch(setError)
              .finally(() => setPending(false));
          }}
        />
      </label>
      {pending && <p className="muted" role="status">Envoi et analyse…</p>}
      {message && <p role="status">{message}</p>}
      {error !== null && <ErrorMessage error={error} />}
    </div>
  );
}

export function EvidenceImage({ evidenceId, alt }: { evidenceId: string; alt: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    binaryRequest(`/hse/evidence/${evidenceId}/content`)
      .then((response) => response.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [evidenceId]);
  if (failed) return <p className="muted small">Photo indisponible.</p>;
  if (!url) return <p className="muted small">Chargement de la photo…</p>;
  return <img src={url} alt={alt} style={{ maxWidth: "100%", maxHeight: 320 }} />;
}

