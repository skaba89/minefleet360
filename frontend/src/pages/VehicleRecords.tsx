import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import {
  DOCUMENT_TYPES,
  label,
  METER_KINDS,
  RESET_REASONS,
  VALIDITY,
  VALIDITY_TONE,
  WITHDRAW_REASONS,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Vehicle = Schemas["VehicleOut"];
type Category = Schemas["VehicleCategoryOut"];
type MeterKind = Schemas["MeterReadingCreate"]["meter_kind"];
type ResetReason = NonNullable<Schemas["MeterReadingCreate"]["reset_reason"]>;
type DocType = Schemas["DocumentCreate"]["doc_type"];
type WithdrawReason = Schemas["DocumentWithdraw"]["reason_code"];
type Doc = Schemas["DocumentOut"];
// Défaut C-06 côté serveur : l'assurance et la visite technique bloquent l'affectation une fois échues.
const BLOCKING_BY_DEFAULT = new Set(["INSURANCE", "TECHNICAL_INSPECTION"]);

/** Relevés de compteur (US-2.09) : ordonnés, en progression plausible, remise à zéro motivée. */
export function Meters({ vehicle: v, category }: { vehicle: Vehicle; category: Category | undefined }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const tz = timezoneOf(v.site_id);
  const [adding, setAdding] = useState(false);
  const kinds = (["ODOMETER_KM", "HOUR_METER"] as const).filter((k) =>
    k === "ODOMETER_KM" ? category?.has_odometer : category?.has_hour_meter,
  );
  const readings = useQuery({
    queryKey: ["meter-readings", v.vehicle_id],
    enabled: kinds.length > 0,
    queryFn: () =>
      read("/vehicles/{vehicle_id}/meter-readings", { path: { vehicle_id: v.vehicle_id }, query: { page_size: 20 } }),
  });
  if (kinds.length === 0) return null;
  const items = readings.data?.items ?? [];
  const latest = (kind: string) => items.find((r) => r.meter_kind === kind);
  const canRecord = v.status !== "RETIRED" && can(me.grants, "fleet.meter.record", v.site_id);
  return (
    <>
      <div className="page-head">
        <h2>Compteurs</h2>
        {canRecord && !adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Nouveau relevé
          </button>
        )}
      </div>
      <dl className="facts">
        {kinds.map((k) => (
          <div className="fact" key={k}>
            <dt>{label(METER_KINDS, k)}</dt>
            <dd>{latest(k) ? `${latest(k)?.value.toLocaleString("fr-FR")} (le ${formatDateTime(latest(k)?.read_at, tz)})` : "—"}</dd>
          </div>
        ))}
      </dl>
      {adding && (
        <ReadingForm
          vehicleId={v.vehicle_id}
          kinds={kinds}
          timeZone={tz}
          onCancel={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            void queryClient.invalidateQueries({ queryKey: ["meter-readings", v.vehicle_id] });
          }}
        />
      )}
      <DataState loading={readings.isLoading} error={readings.error} empty={items.length === 0} emptyText="Aucun relevé.">
        <table>
          <thead>
            <tr>
              <th scope="col">Relevé le</th>
              <th scope="col">Compteur</th>
              <th scope="col">Valeur</th>
              <th scope="col">Remarque</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.vehicle_meter_reading_id}>
                <td>{formatDateTime(r.read_at, tz)}</td>
                <td>{label(METER_KINDS, r.meter_kind)}</td>
                <td>{r.value.toLocaleString("fr-FR")}</td>
                <td>{r.reset_reason ? `Remise à zéro : ${label(RESET_REASONS, r.reset_reason)}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}

function ReadingForm({
  vehicleId,
  kinds,
  timeZone,
  onCancel,
  onDone,
}: {
  vehicleId: string;
  kinds: MeterKind[];
  timeZone: string;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    meter_kind: kinds[0] as string,
    value: "",
    read_at: utcToZonedInput(new Date(), timeZone),
    reset: false,
    reset_reason: "METER_REPLACED",
  });
  return (
    <ActionForm
      title="Nouveau relevé de compteur"
      submitLabel="Enregistrer le relevé"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/vehicles/{vehicle_id}/meter-readings", {
          path: { vehicle_id: vehicleId },
          body: {
            meter_kind: form.meter_kind as MeterKind,
            value: Number(form.value),
            read_at: zonedInputToUtc(form.read_at, timeZone).toISOString(),
            reset_reason: form.reset ? (form.reset_reason as ResetReason) : null,
          },
        })
      }
    >
      <label>
        Compteur
        <select value={form.meter_kind} onChange={(e) => setForm({ ...form, meter_kind: e.target.value })}>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {label(METER_KINDS, k)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Valeur relevée
        <input
          type="number"
          required
          min={0}
          step={0.1}
          value={form.value}
          onChange={(e) => setForm({ ...form, value: e.target.value })}
        />
      </label>
      <label>
        Heure du relevé (heure du site)
        <input type="datetime-local" required value={form.read_at} onChange={(e) => setForm({ ...form, read_at: e.target.value })} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={form.reset} onChange={(e) => setForm({ ...form, reset: e.target.checked })} />
        Remise à zéro (valeur inférieure au relevé précédent)
      </label>
      {form.reset && (
        <label>
          Motif de la remise à zéro
          <select value={form.reset_reason} onChange={(e) => setForm({ ...form, reset_reason: e.target.value })}>
            <Options map={RESET_REASONS} />
          </select>
        </label>
      )}
      <p className="muted small">
        Un relevé ne peut pas être antérieur au précédent ni progresser plus vite que le temps écoulé ne le permet.
      </p>
    </ActionForm>
  );
}

/** Documents réglementaires (US-2.10) : échéances, bloquants pour l'affectation (C-06), retrait motivé. */
export function Documents({ vehicle: v }: { vehicle: Vehicle }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [withdrawing, setWithdrawing] = useState<Doc | null>(null);
  const docs = useQuery({
    queryKey: ["vehicle-documents", v.vehicle_id],
    queryFn: () => read("/vehicles/{vehicle_id}/documents", { path: { vehicle_id: v.vehicle_id } }),
  });
  const canManage = v.status !== "RETIRED" && can(me.grants, "fleet.document.manage", v.site_id);
  const refresh = () => {
    setAdding(false);
    setWithdrawing(null);
    void queryClient.invalidateQueries({ queryKey: ["vehicle-documents"] });
  };
  const items = docs.data ?? [];
  return (
    <>
      <div className="page-head">
        <h2>Documents réglementaires</h2>
        {canManage && !adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Nouveau document
          </button>
        )}
      </div>
      {adding && <DocumentForm vehicleId={v.vehicle_id} onCancel={() => setAdding(false)} onDone={refresh} />}
      {withdrawing && <WithdrawForm doc={withdrawing} onCancel={() => setWithdrawing(null)} onDone={refresh} />}
      <DataState loading={docs.isLoading} error={docs.error} empty={items.length === 0} emptyText="Aucun document enregistré.">
        <table>
          <thead>
            <tr>
              <th scope="col">Type</th>
              <th scope="col">Référence</th>
              <th scope="col">Échéance</th>
              <th scope="col">Validité</th>
              <th scope="col">Bloquant</th>
              {canManage && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.vehicle_document_id}>
                <td>{label(DOCUMENT_TYPES, d.doc_type)}</td>
                <td>
                  {d.reference}
                  {d.issuer && <div className="small muted">{d.issuer}</div>}
                </td>
                <td>{formatDate(d.valid_until)}</td>
                <td>
                  <Badge tone={VALIDITY_TONE[d.validity] ?? "neutral"}>{label(VALIDITY, d.validity)}</Badge>
                  {d.status_reason && <div className="small muted">{label(WITHDRAW_REASONS, d.status_reason)}</div>}
                </td>
                <td>{d.blocks_assignment ? "Oui" : "Non"}</td>
                {canManage && (
                  <td>
                    {d.status === "VALID" && (
                      <button type="button" onClick={() => setWithdrawing(d)}>
                        Retirer
                      </button>
                    )}
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

function DocumentForm({ vehicleId, onCancel, onDone }: { vehicleId: string; onCancel: () => void; onDone: () => void }) {
  const [form, setForm] = useState({
    doc_type: "INSURANCE",
    reference: "",
    issuer: "",
    valid_from: "",
    valid_until: "",
    blocks: true,
  });
  return (
    <ActionForm
      title="Nouveau document"
      submitLabel="Enregistrer le document"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/vehicles/{vehicle_id}/documents", {
          path: { vehicle_id: vehicleId },
          body: {
            doc_type: form.doc_type as DocType,
            reference: form.reference.trim(),
            issuer: form.issuer.trim() || null,
            valid_from: form.valid_from || null,
            valid_until: form.valid_until || null,
            blocks_assignment: form.blocks,
          },
        })
      }
    >
      <label>
        Type de document
        <select
          value={form.doc_type}
          onChange={(e) => setForm({ ...form, doc_type: e.target.value, blocks: BLOCKING_BY_DEFAULT.has(e.target.value) })}
        >
          <Options map={DOCUMENT_TYPES} />
        </select>
      </label>
      <label>
        Référence (numéro du document)
        <input required pattern="[A-Za-z0-9 /._\-]{1,60}" maxLength={60} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
      </label>
      <label>
        Émetteur (facultatif)
        <input maxLength={120} value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
      </label>
      <label>
        Valable à partir du
        <input type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
      </label>
      <label>
        Valable jusqu'au (inclus)
        <input
          type="date"
          required={form.blocks}
          value={form.valid_until}
          onChange={(e) => setForm({ ...form, valid_until: e.target.value })}
        />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={form.blocks} onChange={(e) => setForm({ ...form, blocks: e.target.checked })} />
        Bloque l'affectation du véhicule une fois échu
      </label>
      <p className="muted small">Aucune donnée personnelle dans la référence : uniquement le numéro administratif.</p>
    </ActionForm>
  );
}

function WithdrawForm({ doc, onCancel, onDone }: { doc: Doc; onCancel: () => void; onDone: () => void }) {
  const [reason, setReason] = useState<WithdrawReason>("REPLACED");
  return (
    <ActionForm
      title={`Retirer le document ${doc.reference}`}
      submitLabel="Retirer le document"
      danger
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/vehicle-documents/{vehicle_document_id}/withdraw", {
          path: { vehicle_document_id: doc.vehicle_document_id },
          ifMatch: `"${doc.row_version}"`,
          body: { reason_code: reason },
        })
      }
    >
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value as WithdrawReason)}>
          <Options map={WITHDRAW_REASONS} />
        </select>
      </label>
      <p className="muted small">
        Le document reste dans l'historique. S'il était bloquant, le véhicule ne pourra plus être affecté tant qu'un
        document valide du même type n'est pas enregistré (sauf retrait pour erreur de saisie).
      </p>
    </ActionForm>
  );
}

/** Documents échus ou arrivant à échéance (alerte de conformité), sur le site choisi. */
export function DueDocumentsPage() {
  const { siteId, sites } = useSites();
  const [within, setWithin] = useState(30);
  const due = useQuery({
    queryKey: ["vehicle-documents", "due", siteId, within],
    queryFn: () => read("/vehicle-documents", { query: { site_id: siteId, within_days: within } }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = due.data ?? [];
  return (
    <section>
      <Link className="back" to="/vehicules">
        ← Véhicules
      </Link>
      <div className="page-head">
        <h1>Documents à échéance</h1>
      </div>
      <div className="filters">
        <label>
          Échéance dans les
          <select value={within} onChange={(e) => setWithin(Number(e.target.value))}>
            {[7, 30, 60, 90].map((n) => (
              <option key={n} value={n}>
                {n} jours
              </option>
            ))}
          </select>
        </label>
      </div>
      <DataState loading={due.isLoading} error={due.error} empty={items.length === 0} emptyText="Aucun document à échéance.">
        <table>
          <thead>
            <tr>
              <th scope="col">Véhicule</th>
              <th scope="col">Type</th>
              <th scope="col">Référence</th>
              <th scope="col">Échéance</th>
              <th scope="col">Validité</th>
              <th scope="col">Bloquant</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.vehicle_document_id}>
                <td>
                  <Link to={`/vehicules/${d.vehicle_id}`}>{d.vehicle_fleet_number}</Link>
                  <div className="small muted">{siteCode.get(d.site_id)}</div>
                </td>
                <td>{label(DOCUMENT_TYPES, d.doc_type)}</td>
                <td>{d.reference}</td>
                <td>{formatDate(d.valid_until)}</td>
                <td>
                  <Badge tone={VALIDITY_TONE[d.validity] ?? "neutral"}>{label(VALIDITY, d.validity)}</Badge>
                </td>
                <td>{d.blocks_assignment ? "Oui : affectation refusée une fois échu" : "Non"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}
