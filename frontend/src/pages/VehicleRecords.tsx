import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
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
type ResetReason = Schemas["MeterReset"]["reset_reason"];
type DocType = Schemas["DocumentCreate"]["doc_type"];
type WithdrawReason = Schemas["DocumentWithdraw"]["reason_code"];
type Doc = Schemas["DocumentOut"];
// Seule la carte grise est sans échéance (règle serveur).
const UNDATED = new Set(["REGISTRATION"]);

/** Relevés de compteur (US-2.09) : ordonnés, en progression plausible ; remise à zéro à part. */
export function Meters({ vehicle: v, category }: { vehicle: Vehicle; category: Category | undefined }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const tz = timezoneOf(v.site_id);
  const [panel, setPanel] = useState<"reading" | "reset" | null>(null);
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
  const active = v.status !== "RETIRED";
  const done = () => {
    setPanel(null);
    void queryClient.invalidateQueries({ queryKey: ["meter-readings", v.vehicle_id] });
  };
  return (
    <>
      <div className="page-head">
        <h2>Compteurs</h2>
        <div className="row">
          {active && can(me.grants, "fleet.meter.record", v.site_id) && panel === null && (
            <button type="button" onClick={() => setPanel("reading")}>
              Nouveau relevé
            </button>
          )}
          {active && can(me.grants, "fleet.meter.reset", v.site_id) && panel === null && items.length > 0 && (
            <button type="button" onClick={() => setPanel("reset")}>
              Remise à zéro
            </button>
          )}
        </div>
      </div>
      <dl className="facts">
        {kinds.map((k) => (
          <div className="fact" key={k}>
            <dt>{label(METER_KINDS, k)}</dt>
            <dd>
              {latest(k) ? `${latest(k)?.value.toLocaleString("fr-FR")} (le ${formatDateTime(latest(k)?.read_at, tz)})` : "—"}
            </dd>
          </div>
        ))}
      </dl>
      {panel && <ReadingForm vehicleId={v.vehicle_id} kinds={kinds} timeZone={tz} reset={panel === "reset"} onCancel={() => setPanel(null)} onDone={done} />}
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
  reset,
  onCancel,
  onDone,
}: {
  vehicleId: string;
  kinds: MeterKind[];
  timeZone: string;
  reset: boolean;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    meter_kind: kinds[0] as string,
    value: "",
    read_at: utcToZonedInput(new Date(), timeZone),
    reset_reason: "METER_REPLACED",
  });
  const body = {
    meter_kind: form.meter_kind as MeterKind,
    value: Number(form.value),
    read_at: zonedInputToUtc(form.read_at, timeZone).toISOString(),
  };
  return (
    <ActionForm
      title={reset ? "Remise à zéro du compteur" : "Nouveau relevé de compteur"}
      submitLabel={reset ? "Enregistrer la remise à zéro" : "Enregistrer le relevé"}
      danger={reset}
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        reset
          ? call("post", "/vehicles/{vehicle_id}/meter-resets", {
              path: { vehicle_id: vehicleId },
              body: { ...body, reset_reason: form.reset_reason as ResetReason },
            })
          : call("post", "/vehicles/{vehicle_id}/meter-readings", { path: { vehicle_id: vehicleId }, body })
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
        {reset ? "Nouvelle valeur (inférieure au dernier relevé)" : "Valeur relevée"}
        <input type="number" required min={0} step={0.1} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
      </label>
      <label>
        Heure du relevé (heure du site)
        <input type="datetime-local" required value={form.read_at} onChange={(e) => setForm({ ...form, read_at: e.target.value })} />
      </label>
      {reset && (
        <label>
          Motif de la remise à zéro
          <select value={form.reset_reason} onChange={(e) => setForm({ ...form, reset_reason: e.target.value })}>
            <Options map={RESET_REASONS} />
          </select>
        </label>
      )}
      <p className="muted small">
        {reset
          ? "Réservée à l'atelier et à l'exploitation ; la valeur précédente reste dans l'historique et le journal."
          : "Un relevé ne peut pas être antérieur au précédent, ni en baisse, ni progresser plus vite que le temps écoulé ne le permet."}
      </p>
    </ActionForm>
  );
}

/** Documents réglementaires (US-2.10, D-42) : exigés selon la catégorie, immuables, retrait motivé. */
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
  const items = docs.data?.documents ?? [];
  const missing = docs.data?.missing_types ?? [];
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
      {missing.length > 0 && (
        <p className="warn-text" role="status">
          Documents exigés manquants ou non valides : {missing.map((t) => label(DOCUMENT_TYPES, t)).join(", ")}.
        </p>
      )}
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
              <th scope="col">Exigé</th>
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
                <td>{d.valid_until ? formatDate(d.valid_until) : "Sans échéance"}</td>
                <td>
                  <Badge tone={VALIDITY_TONE[d.validity] ?? "neutral"}>{label(VALIDITY, d.validity)}</Badge>
                  {d.status_reason && <div className="small muted">{label(WITHDRAW_REASONS, d.status_reason)}</div>}
                </td>
                <td>{d.required ? "Oui" : "Non"}</td>
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
  const [form, setForm] = useState({ doc_type: "INSURANCE", reference: "", issuer: "", valid_from: "", valid_until: "" });
  const undated = UNDATED.has(form.doc_type);
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
          },
        })
      }
    >
      <label>
        Type de document
        <select value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}>
          <Options map={DOCUMENT_TYPES} />
        </select>
      </label>
      <label>
        Référence (numéro du document)
        <input required pattern="[A-Za-z0-9 /._\-]{1,60}" maxLength={60} value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
      </label>
      <label>
        Organisme émetteur (facultatif)
        <input maxLength={120} value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
      </label>
      <label>
        Valable à partir du
        <input type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
      </label>
      <label>
        Valable jusqu'au (inclus){undated ? " — facultatif" : ""}
        <input type="date" required={!undated} value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} />
      </label>
      <p className="muted small">
        Un document enregistré ne se modifie plus : en cas d'erreur, retirez-le puis saisissez-en un nouveau. Aucune
        donnée personnelle : uniquement le numéro administratif et le nom de l'organisme.
      </p>
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
        Le document reste dans l'historique. S'il est exigé pour ce véhicule, celui-ci ne pourra plus être affecté tant
        qu'un document valide du même type n'est pas enregistré. « Erreur de saisie » n'est possible que dans les 24
        heures suivant l'enregistrement.
      </p>
    </ActionForm>
  );
}

/** Documents échus ou arrivant à échéance (alerte de conformité), sur le site choisi. */
export function DueDocumentsPage() {
  const { siteId, sites } = useSites();
  const [within, setWithin] = useState(45);
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
            {[7, 30, 45, 60, 90].map((n) => (
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
              <th scope="col">Exigé</th>
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
                <td>{d.required ? "Oui : affectation refusée une fois échu" : "Non"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}

/** Administration : documents exigés par catégorie de véhicule (D-42). */
export function RequiredDocumentsPage() {
  const categories = useQuery({ queryKey: ["vehicle-categories"], queryFn: () => read("/vehicle-categories") });
  const items = (categories.data ?? []).filter((c) => c.is_active);
  return (
    <>
      <h2>Documents exigés par catégorie de véhicule</h2>
      <p className="muted small">
        Un véhicule doit avoir un exemplaire valide de chaque document coché pour sa catégorie : sinon l'affectation est
        refusée (document échu ou retiré) ou signalée (document jamais saisi, selon la politique de déploiement). Valeurs
        par défaut proposées par l'expert flotte ; la liste légale est à valider localement.
      </p>
      <DataState loading={categories.isLoading} error={categories.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Catégorie</th>
              {Object.entries(DOCUMENT_TYPES).map(([code, text]) => (
                <th scope="col" key={code}>
                  {text}
                </th>
              ))}
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <CategoryRow key={c.vehicle_category_id} category={c} />
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}

function CategoryRow({ category }: { category: Category }) {
  const queryClient = useQueryClient();
  const required = useQuery({
    queryKey: ["required-documents", category.vehicle_category_id],
    queryFn: () =>
      read("/vehicle-categories/{category_id}/required-documents", {
        path: { category_id: category.vehicle_category_id },
      }),
  });
  const [draft, setDraft] = useState<Set<string> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const current = new Set(required.data?.doc_types ?? []);
  const selected = draft ?? current;
  const toggle = (code: string) => {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setDraft(next);
  };
  async function save() {
    setError(null);
    try {
      await call("put", "/vehicle-categories/{category_id}/required-documents", {
        path: { category_id: category.vehicle_category_id },
        body: { doc_types: [...selected] as DocType[] },
      });
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ["required-documents", category.vehicle_category_id] });
    } catch (err) {
      setError(err);
    }
  }
  return (
    <tr>
      <th scope="row">{category.label_fr}</th>
      {Object.keys(DOCUMENT_TYPES).map((code) => (
        <td key={code}>
          <input
            type="checkbox"
            aria-label={`${category.label_fr} : ${label(DOCUMENT_TYPES, code)}`}
            checked={selected.has(code)}
            disabled={!required.isSuccess}
            onChange={() => toggle(code)}
          />
        </td>
      ))}
      <td>
        {draft && (
          <button type="button" className="primary" onClick={() => void save()}>
            Enregistrer
          </button>
        )}
        {error !== null && <ErrorMessage error={error} />}
      </td>
    </tr>
  );
}
