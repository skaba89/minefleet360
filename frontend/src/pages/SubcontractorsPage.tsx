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
      {can(me.grants, "partner.performance.read") && <PerformanceSection />}
    </>
  );
}

const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const PERIODS: Record<string, string> = { "30": "30 jours", "90": "90 jours", "365": "12 mois" };

function hours(value: string | null | undefined): string {
  return value == null ? "—" : `${number.format(Number(value))} h`;
}

/** Performance mesurée des engins rattachés (tranche 3) comparée à l'objectif SLA saisi par le donneur d'ordre. */
function PerformanceSection() {
  const [days, setDays] = useState("90");
  const report = useQuery({
    queryKey: ["subcontractor-performance", days],
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - Number(days) * 24 * 3600 * 1000);
      return read("/subcontractors/performance", { query: { from: from.toISOString(), to: to.toISOString() } });
    },
  });
  const rows = report.data?.subcontractors ?? [];
  return (
    <section aria-label="Performance des sous-traitants">
      <div className="page-head">
        <h2>Performance mesurée</h2>
        <label>
          Période
          <select value={days} onChange={(e) => setDays(e.target.value)}>
            {Object.entries(PERIODS).map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </div>
      <DataState loading={report.isLoading} error={report.error} empty={rows.length === 0} emptyText="Aucun sous-traitant.">
        <table>
          <thead>
            <tr>
              <th scope="col">Sous-traitant</th>
              <th scope="col">Engins</th>
              <th scope="col">Disponibilité</th>
              <th scope="col">Objectif SLA</th>
              <th scope="col">Pannes</th>
              <th scope="col">MTBF</th>
              <th scope="col">MTTR</th>
              {report.data?.tonnage_visible && <th scope="col">Productivité</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.subcontractor_id}>
                <td>
                  {r.code}
                  <div className="small muted">{r.legal_name}</div>
                </td>
                <td>{r.vehicles}</td>
                <td>{r.availability_percent == null ? "—" : `${number.format(Number(r.availability_percent))} %`}</td>
                <td>
                  {r.availability_target_percent == null ? (
                    "—"
                  ) : (
                    <>
                      {number.format(Number(r.availability_target_percent))} %{" "}
                      {r.sla_met != null && <Badge tone={r.sla_met ? "ok" : "bad"}>{r.sla_met ? "Atteint" : "Non atteint"}</Badge>}
                    </>
                  )}
                </td>
                <td>{r.failures}</td>
                <td>{hours(r.mtbf_hours)}</td>
                <td>{hours(r.mttr_hours)}</td>
                {report.data?.tonnage_visible && (
                  <td>
                    {r.tonnes_per_operating_hour == null ? "—" : `${number.format(Number(r.tonnes_per_operating_hour))} t/h moteur`}
                    {r.tonnage_pending && <div className="small warn-text">pesées en attente non comptées</div>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      <p className="muted small">
        Mesures calculées à partir des engins rattachés (ordres de travail, horamètre, pesées valides), dans votre portée ;
        aucune valeur déclarée par le sous-traitant.
      </p>
    </section>
  );
}

function CreateForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [form, setForm] = useState({
    code: "",
    legal_name: "",
    registration_number: "",
    tax_id: "",
    country_code: "GN",
    availability_target_percent: "",
  });
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
            availability_target_percent: orNull(form.availability_target_percent),
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
      <label>
        Objectif de disponibilité (SLA, %, facultatif)
        <input
          type="number"
          min={0}
          max={100}
          step="0.01"
          value={form.availability_target_percent}
          onChange={(e) => setForm({ ...form, availability_target_percent: e.target.value })}
        />
      </label>
    </ActionForm>
  );
}

function EditForm({ item, onCancel, onDone }: { item: Subcontractor; onCancel: () => void; onDone: () => void }) {
  const [legalName, setLegalName] = useState(item.legal_name);
  const [notes, setNotes] = useState(item.notes ?? "");
  const [target, setTarget] = useState(item.availability_target_percent ?? "");
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
        if (target !== (item.availability_target_percent ?? "") && target !== "") body.availability_target_percent = target;
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
        Objectif de disponibilité (SLA, %)
        <input type="number" min={0} max={100} step="0.01" value={target} onChange={(e) => setTarget(e.target.value)} />
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
