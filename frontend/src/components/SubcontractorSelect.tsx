import { useQuery } from "@tanstack/react-query";

import { read } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { can } from "../lib/permissions";

/** Libellé d'un sous-traitant rattaché ; « Rattaché » sans droit de lecture du référentiel. */
export function useSubcontractorName(subcontractorId: string | null | undefined): string | null {
  const me = useMe();
  const readable = can(me.grants, "partner.subcontractor.read");
  const list = useQuery({
    queryKey: ["subcontractors", ""],
    enabled: !!subcontractorId && readable,
    queryFn: () => read("/subcontractors", { query: { status: null } }),
  });
  if (!subcontractorId) return null;
  const found = (list.data ?? []).find((s) => s.subcontractor_id === subcontractorId);
  return found ? `${found.code} — ${found.legal_name}` : "Rattaché au référentiel";
}

/**
 * Choix du sous-traitant d'un engin SUBCONTRACTED (lot 1, tranche 2) : sous-traitants actifs, plus le sous-traitant
 * actuel même s'il est suspendu (un rattachement existant reste valable). Masqué sans droit de lecture du référentiel.
 */
export function SubcontractorSelect({
  value,
  current,
  onChange,
}: {
  value: string;
  current: string | null;
  /** Identifiant choisi (vide = non rattaché) et raison sociale correspondante (pour pré-remplir un libellé). */
  onChange: (value: string, legalName: string | null) => void;
}) {
  const me = useMe();
  const readable = can(me.grants, "partner.subcontractor.read");
  const list = useQuery({
    queryKey: ["subcontractors", ""],
    enabled: readable,
    queryFn: () => read("/subcontractors", { query: { status: null } }),
  });
  if (!readable) return null;
  const options = (list.data ?? []).filter((s) => s.status === "ACTIVE" || s.subcontractor_id === current);
  return (
    <label>
      Sous-traitant (référentiel)
      <select
        value={value}
        onChange={(e) => onChange(e.target.value, options.find((s) => s.subcontractor_id === e.target.value)?.legal_name ?? null)}
      >
        <option value="">— Non rattaché —</option>
        {options.map((s) => (
          <option key={s.subcontractor_id} value={s.subcontractor_id}>
            {s.code} — {s.legal_name}
            {s.status !== "ACTIVE" ? " (non actif)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
