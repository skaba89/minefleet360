import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, Badge, DataState } from "../components/common";
import { ActionForm, orNull } from "../components/forms";
import { can } from "../lib/permissions";

type Subcontractor = Schemas["SubcontractorOut"];
type Status = Subcontractor["status"];

const STATUS_LABEL: Record<Status, string> = { ACTIVE: "Active", SUSPENDED: "Suspendue", ENDED: "Relation terminée" };
const STATUS_TONE: Record<Status, "ok" | "warn" | "neutral"> = { ACTIVE: "ok", SUSPENDED: "warn", ENDED: "neutral" };

/**
 * Référentiel des organisations sous-traitantes (lot 1) : données du donneur d'ordre, vues par ses rôles
 * internes seulement. Aucun compte externe n'est créé ici ; aucune donnée nominative n'est saisie.
 */
export function SubcontractorsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const canManage = can(me.grants, "partner.subcontractor.manage");
  const [filter, setFilter] = useState<Status | "">("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Subcontractor | null>(null);
  const list = useQuery({
    queryKey: ["subcontractors", filter],
    enabled: can(me.grants, "partner.subcontractor.read"),
    queryFn: () => read("/subcontractors", { query: { status: filter || null } }),
  });
  if (!can(me.grants, "partner.subcontractor.read")) return <AccessDenied />;
  const refresh = () => {
    setCreating(false);
    setEditing(null);
    void queryClient.invalidateQueries({ queryKey: ["subcontractors"] });
  };
  const items = list.data ?? [];
  return (
    <>
      <div className="page-head">
        <h2>Sous-traitants</h2>
        {canManage && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouveau sous-traitant
          </button>
        )}
      </div>
      <p className="muted small">
        Organisations intervenant pour votre compte. Aucune donnée nominative ; les contrats restent gérés dans Juridique.
      </p>
      {creating && <CreateForm onCancel={() => setCreating(false)} onDone={refresh} />}
      {editing && <EditForm item={editing} onCancel={() => setEditing(null)} onDone={refresh} />}
      <div className="filters">
        <label>
          Filtrer par statut
          <select value={filter} onChange={(e) => setFilter(e.target.value as Status | "")}>
            <option value="">Tous</option>
            {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
      </div>
      <DataState loading={list.isLoading} error={list.error} empty={items.length === 0} emptyText="Aucun sous-traitant enregistré.">
        <table>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Raison sociale</th>
              <th scope="col">RCCM / NIF</th>
              <th scope="col">Statut</th>
              {canManage && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.subcontractor_id}>
                <td>{s.code}</td>
                <td>
                  {s.legal_name}
                  <div className="small muted">{s.country_code}</div>
                </td>
                <td>
                  {s.registration_number ?? "—"}
                  <div className="small muted">{s.tax_id ?? "—"}</div>
                </td>
                <td>
                  <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>
                  {s.status_reason && <div className="small muted">{s.status_reason}</div>}
                </td>
                {canManage && (
                  <td>
                    <button type="button" onClick={() => setEditing(s)}>
                      Modifier
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}

function CreateForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ code: "", legal_name: "", registration_number: "", tax_id: "", country_code: "GN" });
  return (
    <ActionForm
      title="Nouveau sous-traitant"
      submitLabel="Créer le sous-traitant"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/subcontractors", {
          body: {
            code: form.code.trim(),
            legal_name: form.legal_name.trim(),
            registration_number: orNull(form.registration_number),
            tax_id: orNull(form.tax_id),
            country_code: form.country_code.trim().toUpperCase(),
          },
        })
      }
    >
      <label>
        Code (unique)
        <input required pattern="[A-Za-z0-9_\-]{1,32}" maxLength={32} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
      </label>
      <label>
        Raison sociale
        <input required maxLength={240} value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} />
      </label>
      <label>
        RCCM (facultatif)
        <input maxLength={64} value={form.registration_number} onChange={(e) => setForm({ ...form, registration_number: e.target.value })} />
      </label>
      <label>
        NIF (facultatif)
        <input maxLength={64} value={form.tax_id} onChange={(e) => setForm({ ...form, tax_id: e.target.value })} />
      </label>
      <label>
        Pays (code ISO)
        <input required pattern="[A-Za-z]{2}" maxLength={2} value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value })} />
      </label>
    </ActionForm>
  );
}

function EditForm({ item, onCancel, onDone }: { item: Subcontractor; onCancel: () => void; onDone: () => void }) {
  const [legalName, setLegalName] = useState(item.legal_name);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [status, setStatus] = useState<Status>(item.status);
  const [reason, setReason] = useState("");
  const statusChanged = status !== item.status;
  return (
    <ActionForm
      title={`Modifier ${item.code}`}
      submitLabel="Enregistrer"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() => {
        const body: Schemas["SubcontractorUpdate"] = {};
        if (legalName.trim() !== item.legal_name) body.legal_name = legalName.trim();
        if (notes !== (item.notes ?? "")) body.notes = notes;
        if (statusChanged) {
          body.status = status;
          if (status !== "ACTIVE") body.status_reason = reason.trim();
        }
        return call("patch", "/subcontractors/{subcontractor_id}", {
          path: { subcontractor_id: item.subcontractor_id },
          body,
          ifMatch: `"${item.row_version}"`,
        });
      }}
    >
      <label>
        Raison sociale
        <input required maxLength={240} value={legalName} onChange={(e) => setLegalName(e.target.value)} />
      </label>
      <label>
        Notes (sans donnée nominative)
        <textarea maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <label>
        Statut
        <select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
          {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      {statusChanged && status !== "ACTIVE" && (
        <label>
          Motif (obligatoire)
          <input required minLength={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
      )}
    </ActionForm>
  );
}
