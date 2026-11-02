import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm, Fact, Options, orNull } from "../components/forms";
import {
  HSE_ACTION_REASONS,
  HSE_ACTION_STATUS,
  HSE_ACTION_TONE,
  HSE_CANCEL_REASONS,
  HSE_CATEGORY,
  HSE_EVENTS,
  HSE_SEVERITY,
  HSE_SEVERITY_TONE,
  HSE_STATUS,
  HSE_TONE,
  label,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Incident = Schemas["IncidentOut"];
type CorrectiveAction = Schemas["ActionOut"];
type Status = Incident["status"];
type Category = Schemas["IncidentCreate"]["category"];
type Severity = Schemas["IncidentCreate"]["severity"];
type CancelReason = NonNullable<Schemas["IncidentTransition"]["reason_code"]>;
type ActionReason = NonNullable<Schemas["ActionDecisionIn"]["reason_code"]>;
const PAGE_SIZE = 50;

/** HSE (lot HSE-1) : registre des incidents, indicateurs de la période et actions dont je suis responsable. */
export function HsePage() {
  const me = useMe();
  const { siteId, sites, timezoneOf } = useSites();
  const [status, setStatus] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [page, setPage] = useState(1);
  const [reporting, setReporting] = useState(false);
  const canRead = can(me.grants, "hse.incident.read", siteId);
  const incidents = useQuery({
    queryKey: ["hse-incidents", siteId, status, openOnly, page],
    enabled: canRead,
    queryFn: () =>
      read("/hse/incidents", {
        query: { site_id: siteId, status: (status || null) as Status | null, open_only: openOnly, page, page_size: PAGE_SIZE },
      }),
  });
  const summary = useQuery({
    queryKey: ["hse-summary", siteId],
    enabled: canRead,
    queryFn: () => read("/hse/summary", { query: { site_id: siteId, days: 90 } }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = incidents.data?.items ?? [];
  const s = summary.data;
  return (
    <section>
      <div className="page-head">
        <h1>Sécurité (HSE)</h1>
        {can(me.grants, "hse.incident.report", siteId) && !reporting && (
          <button type="button" className="primary" onClick={() => setReporting(true)}>
            Déclarer un incident
          </button>
        )}
      </div>
      {reporting && <ReportIncidentForm onClose={() => setReporting(false)} />}
      {!canRead && (
        <p className="muted">
          Vous pouvez déclarer un incident ; le registre est réservé aux responsables HSE et à l'encadrement.
        </p>
      )}
      {canRead && s && (
        <dl className="facts" aria-label="Indicateurs HSE sur 90 jours">
          <Fact label="Incidents (90 j)">{s.incidents}</Fact>
          <Fact label="Blessés (90 j)">{s.injured}</Fact>
          <Fact label="Avec arrêt de travail">{s.lost_time_incidents}</Fact>
          <Fact label="Incidents ouverts">{s.open_incidents}</Fact>
          <Fact label="Actions en cours">{s.open_actions}</Fact>
          <Fact label="Actions en retard">
            {s.overdue_actions > 0 ? <Badge tone="bad">{s.overdue_actions}</Badge> : 0}
          </Fact>
        </dl>
      )}
      {canRead && <MyActions />}
      {canRead && (
        <>
          <h2>Registre des incidents</h2>
          <div className="filters">
            <label>
              Statut
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <Options map={HSE_STATUS} empty="Tous" />
              </select>
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={openOnly}
                onChange={(e) => {
                  setOpenOnly(e.target.checked);
                  setPage(1);
                }}
              />
              Ouverts seulement
            </label>
          </div>
          <DataState loading={incidents.isLoading} error={incidents.error} empty={items.length === 0} emptyText="Aucun incident.">
            <table>
              <thead>
                <tr>
                  <th scope="col">Incident</th>
                  <th scope="col">Nature</th>
                  <th scope="col">Gravité</th>
                  <th scope="col">Engin</th>
                  <th scope="col">Actions</th>
                  <th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.hse_incident_id}>
                    <td>
                      <Link to={`/hse/${i.hse_incident_id}`}>{i.reference}</Link> — {i.title}
                      <div className="small muted">
                        {siteCode.get(i.site_id)} — {formatDateTime(i.occurred_at, timezoneOf(i.site_id))}
                      </div>
                    </td>
                    <td>{label(HSE_CATEGORY, i.category)}</td>
                    <td>
                      <Badge tone={HSE_SEVERITY_TONE[i.severity] ?? "neutral"}>{label(HSE_SEVERITY, i.severity)}</Badge>
                    </td>
                    <td>{i.vehicle_fleet_number ?? "—"}</td>
                    <td>
                      {i.open_actions}
                      {i.overdue_actions > 0 && <div className="warn-text small">{i.overdue_actions} en retard</div>}
                    </td>
                    <td>
                      <Badge tone={HSE_TONE[i.status] ?? "neutral"}>{label(HSE_STATUS, i.status)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={page} pageSize={PAGE_SIZE} total={incidents.data?.total ?? 0} onPage={setPage} />
          </DataState>
        </>
      )}
    </section>
  );
}

function MyActions() {
  const actions = useQuery({
    queryKey: ["hse-actions", "mine"],
    queryFn: () => read("/hse/corrective-actions", { query: { mine: true, open_only: true, page_size: 100 } }),
  });
  const items = (actions.data?.items ?? []).filter((a) => a.status === "OPEN");
  if (items.length === 0) return null;
  return (
    <>
      <h2>Mes actions correctives à réaliser</h2>
      <ul>
        {items.map((a) => (
          <li key={a.hse_corrective_action_id}>
            <Link to={`/hse/${a.hse_incident_id}`}>{a.incident_reference}</Link> — {a.title} — échéance {formatDate(a.due_date)}{" "}
            {a.overdue && <Badge tone="bad">En retard</Badge>}
          </li>
        ))}
      </ul>
    </>
  );
}

function ReportIncidentForm({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, sites, timezoneOf } = useSites();
  const [form, setForm] = useState({
    site_id: siteId ?? sites[0]?.site_id ?? "",
    category: "NEAR_MISS",
    severity: "LOW",
    title: "",
    description: "",
    occurred_at: utcToZonedInput(new Date(), timezoneOf(siteId)),
    location_note: "",
    vehicle_id: "",
    injured_count: "0",
    lost_time: false,
    immediate_actions: "",
  });
  const vehicles = useQuery({
    queryKey: ["vehicles", "hse", form.site_id],
    enabled: !!form.site_id && can(me.grants, "fleet.vehicle.read", form.site_id),
    queryFn: () => read("/vehicles", { query: { site_id: form.site_id, page_size: 200 } }),
  });
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  return (
    <ActionForm
      title="Déclarer un incident"
      submitLabel="Enregistrer la déclaration"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/hse/incidents", {
          body: {
            site_id: form.site_id,
            category: form.category as Category,
            severity: form.severity as Severity,
            title: form.title.trim(),
            description: form.description.trim(),
            occurred_at: zonedInputToUtc(form.occurred_at, timezoneOf(form.site_id)).toISOString(),
            location_note: orNull(form.location_note),
            vehicle_id: form.vehicle_id || null,
            injured_count: Number(form.injured_count) || 0,
            lost_time: form.lost_time,
            immediate_actions: orNull(form.immediate_actions),
          },
        });
        void queryClient.invalidateQueries({ queryKey: ["hse-incidents"] });
        void queryClient.invalidateQueries({ queryKey: ["hse-summary"] });
        if (can(me.grants, "hse.incident.read", data.site_id)) navigate(`/hse/${data.hse_incident_id}`);
        else onClose();
      }}
    >
      <label>
        Site
        <select required value={form.site_id} onChange={(e) => set({ site_id: e.target.value, vehicle_id: "" })}>
          <option value="">— Choisir —</option>
          {sites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Nature
        <select value={form.category} onChange={(e) => set({ category: e.target.value })}>
          <Options map={HSE_CATEGORY} />
        </select>
      </label>
      <label>
        Gravité estimée
        <select value={form.severity} onChange={(e) => set({ severity: e.target.value })}>
          <Options map={HSE_SEVERITY} />
        </select>
      </label>
      <label>
        Survenu le (heure du site)
        <input type="datetime-local" required value={form.occurred_at} onChange={(e) => set({ occurred_at: e.target.value })} />
      </label>
      <label>
        Titre
        <input required minLength={3} maxLength={200} value={form.title} onChange={(e) => set({ title: e.target.value })} />
      </label>
      <label>
        Description des faits
        <textarea required minLength={10} maxLength={4000} value={form.description} onChange={(e) => set({ description: e.target.value })} />
      </label>
      <label>
        Lieu (facultatif)
        <input maxLength={200} value={form.location_note} onChange={(e) => set({ location_note: e.target.value })} />
      </label>
      {vehicles.data && (
        <label>
          Engin impliqué (facultatif)
          <select value={form.vehicle_id} onChange={(e) => set({ vehicle_id: e.target.value })}>
            <option value="">— Aucun —</option>
            {vehicles.data.items.map((v) => (
              <option key={v.vehicle_id} value={v.vehicle_id}>
                {v.fleet_number}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Nombre de blessés
        <input type="number" min={0} max={500} value={form.injured_count} onChange={(e) => set({ injured_count: e.target.value })} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={form.lost_time} onChange={(e) => set({ lost_time: e.target.checked })} />
        Arrêt de travail
      </label>
      <label>
        Mesures immédiates prises (facultatif)
        <textarea maxLength={2000} value={form.immediate_actions} onChange={(e) => set({ immediate_actions: e.target.value })} />
      </label>
      <p className="muted small">Décrivez les faits sans nom de victime ni information médicale.</p>
    </ActionForm>
  );
}

type Panel = "note" | "close" | "cancel" | "action" | null;

/** Fiche d'un incident : enquête, actions correctives, clôture et chronologie. */
export function HseIncidentPage() {
  const { incidentId = "" } = useParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<unknown>(null);
  const incident = useQuery({
    queryKey: ["hse-incident", incidentId],
    queryFn: () => call("get", "/hse/incidents/{hse_incident_id}", { path: { hse_incident_id: incidentId } }),
  });
  const i = incident.data?.data;
  const etag = incident.data?.etag ?? null;
  const tz = timezoneOf(i?.site_id);
  const canManage = i ? can(me.grants, "hse.incident.manage", i.site_id) : false;
  const open = i ? i.status === "REPORTED" || i.status === "INVESTIGATING" : false;
  const refresh = async () => {
    setPanel(null);
    await queryClient.invalidateQueries({ queryKey: ["hse-incident", incidentId] });
    void queryClient.invalidateQueries({ queryKey: ["hse-incidents"] });
    void queryClient.invalidateQueries({ queryKey: ["hse-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["hse-actions"] });
  };
  async function transition(body: Schemas["IncidentTransition"]) {
    await call("post", "/hse/incidents/{hse_incident_id}/transition", {
      path: { hse_incident_id: incidentId },
      ifMatch: etag,
      body,
    });
    await refresh();
  }

  return (
    <section>
      <Link className="back" to="/hse">
        ← Sécurité (HSE)
      </Link>
      <DataState loading={incident.isLoading} error={incident.error} empty={!i}>
        {i && (
          <>
            <div className="page-head">
              <h1>
                {i.reference} — {i.title} <Badge tone={HSE_TONE[i.status] ?? "neutral"}>{label(HSE_STATUS, i.status)}</Badge>
              </h1>
            </div>
            {canManage && open && (
              <div className="toolbar">
                {i.status === "REPORTED" && (
                  <button
                    type="button"
                    className="primary"
                    onClick={() => {
                      setError(null);
                      transition({ action: "START_INVESTIGATION" }).catch(setError);
                    }}
                  >
                    Ouvrir l'enquête
                  </button>
                )}
                {i.status === "INVESTIGATING" && (
                  <>
                    <button type="button" onClick={() => setPanel("note")}>
                      Mettre à jour l'enquête
                    </button>
                    <button type="button" className="primary" onClick={() => setPanel("close")}>
                      Clôturer
                    </button>
                  </>
                )}
                <button type="button" onClick={() => setPanel("action")}>
                  Ajouter une action corrective
                </button>
                <button type="button" onClick={() => setPanel("cancel")}>
                  Annuler la déclaration
                </button>
              </div>
            )}
            {error !== null && <ErrorMessage error={error} />}
            {panel === "note" && <InvestigationForm incident={i} closing={false} onCancel={() => setPanel(null)} onSubmit={transition} />}
            {panel === "close" && <InvestigationForm incident={i} closing onCancel={() => setPanel(null)} onSubmit={transition} />}
            {panel === "cancel" && <CancelIncidentForm onCancel={() => setPanel(null)} onSubmit={(r) => transition({ action: "CANCEL", reason_code: r })} />}
            {panel === "action" && <AddActionForm incident={i} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
            <dl className="facts">
              <Fact label="Nature">{label(HSE_CATEGORY, i.category)}</Fact>
              <Fact label="Gravité">
                <Badge tone={HSE_SEVERITY_TONE[i.severity] ?? "neutral"}>{label(HSE_SEVERITY, i.severity)}</Badge>
              </Fact>
              <Fact label="Survenu le">{formatDateTime(i.occurred_at, tz)}</Fact>
              <Fact label="Déclaré le">{formatDateTime(i.reported_at, tz)}</Fact>
              <Fact label="Déclarant">{i.reported_by_name}</Fact>
              <Fact label="Lieu">{i.location_note}</Fact>
              <Fact label="Engin impliqué">
                {i.vehicle_id ? <Link to={`/vehicules/${i.vehicle_id}`}>{i.vehicle_fleet_number}</Link> : null}
              </Fact>
              <Fact label="Blessés">{i.injured_count}</Fact>
              <Fact label="Arrêt de travail">{i.lost_time ? "Oui" : "Non"}</Fact>
              <Fact label="Description">{i.description}</Fact>
              <Fact label="Mesures immédiates">{i.immediate_actions}</Fact>
              <Fact label="Cause racine">{i.root_cause}</Fact>
              <Fact label="Synthèse d'enquête">{i.investigation_summary}</Fact>
              <Fact label="Motif d'annulation">{i.status_reason ? label(HSE_CANCEL_REASONS, i.status_reason) : null}</Fact>
              <Fact label="Clôturé le">{i.closed_at ? formatDateTime(i.closed_at, tz) : null}</Fact>
            </dl>
            <h2>Actions correctives</h2>
            <ActionsTable incident={i} canManage={canManage} onChanged={() => void refresh()} />
            <h2>Chronologie</h2>
            <ol className="timeline">
              {(i.events ?? []).map((e, n) => (
                <li key={`${e.occurred_at}-${n}`}>
                  <strong>{label(HSE_EVENTS, e.event_type)}</strong> — {formatDateTime(e.occurred_at, tz)}
                  {e.actor_name && <span className="muted"> par {e.actor_name}</span>}
                  {e.reason && (
                    <span className="muted"> ({label({ ...HSE_CANCEL_REASONS, ...HSE_ACTION_REASONS }, e.reason)})</span>
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </DataState>
    </section>
  );
}

function InvestigationForm({
  incident,
  closing,
  onCancel,
  onSubmit,
}: {
  incident: Incident;
  closing: boolean;
  onCancel: () => void;
  onSubmit: (body: Schemas["IncidentTransition"]) => Promise<unknown>;
}) {
  const [form, setForm] = useState({
    root_cause: incident.root_cause ?? "",
    investigation_summary: incident.investigation_summary ?? "",
    severity: incident.severity as string,
    category: incident.category as string,
  });
  const changed = (value: string, original: string | null | undefined) => (value.trim() && value.trim() !== (original ?? "") ? value.trim() : null);
  return (
    <ActionForm
      title={closing ? "Clôturer l'incident" : "Mettre à jour l'enquête"}
      submitLabel={closing ? "Clôturer" : "Enregistrer"}
      onCancel={onCancel}
      onSubmit={() =>
        onSubmit({
          action: closing ? "CLOSE" : "NOTE",
          root_cause: changed(form.root_cause, incident.root_cause),
          investigation_summary: changed(form.investigation_summary, incident.investigation_summary),
          severity: form.severity !== incident.severity ? (form.severity as Severity) : null,
          category: form.category !== incident.category ? (form.category as Category) : null,
        })
      }
    >
      <label>
        Cause racine
        <textarea required={closing} maxLength={4000} value={form.root_cause} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} />
      </label>
      <label>
        Synthèse d'enquête
        <textarea maxLength={4000} value={form.investigation_summary} onChange={(e) => setForm({ ...form, investigation_summary: e.target.value })} />
      </label>
      <label>
        Gravité
        <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
          <Options map={HSE_SEVERITY} />
        </select>
      </label>
      <label>
        Nature
        <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          <Options map={HSE_CATEGORY} />
        </select>
      </label>
      {closing && (
        <p className="muted small">
          La clôture exige que toutes les actions soient vérifiées ou annulées, au moins une action vérifiée pour un incident
          grave, et qu'elle soit faite par une autre personne que le déclarant.
        </p>
      )}
    </ActionForm>
  );
}

function CancelIncidentForm({ onCancel, onSubmit }: { onCancel: () => void; onSubmit: (reason: CancelReason) => Promise<unknown> }) {
  const [reason, setReason] = useState("DUPLICATE");
  return (
    <ActionForm title="Annuler la déclaration" submitLabel="Annuler la déclaration" danger onCancel={onCancel} onSubmit={() => onSubmit(reason as CancelReason)}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          <Options map={HSE_CANCEL_REASONS} />
        </select>
      </label>
    </ActionForm>
  );
}

function AddActionForm({ incident, onCancel, onDone }: { incident: Incident; onCancel: () => void; onDone: () => void }) {
  const owners = useQuery({
    queryKey: ["hse-action-owners", incident.hse_incident_id],
    queryFn: () =>
      call("get", "/hse/incidents/{hse_incident_id}/action-owners", { path: { hse_incident_id: incident.hse_incident_id } }),
  });
  const [form, setForm] = useState({ title: "", description: "", owner_user_id: "", due_date: "" });
  return (
    <ActionForm
      title="Ajouter une action corrective"
      submitLabel="Ajouter"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/hse/incidents/{hse_incident_id}/actions", {
          path: { hse_incident_id: incident.hse_incident_id },
          body: {
            title: form.title.trim(),
            description: orNull(form.description),
            owner_user_id: form.owner_user_id,
            due_date: form.due_date,
          },
        })
      }
    >
      <label>
        Action
        <input required minLength={3} maxLength={200} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      </label>
      <label>
        Détail (facultatif)
        <textarea maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </label>
      <label>
        Responsable
        <select required value={form.owner_user_id} onChange={(e) => setForm({ ...form, owner_user_id: e.target.value })}>
          <option value="">— Choisir —</option>
          {(owners.data?.data ?? []).map((o) => (
            <option key={o.user_account_id} value={o.user_account_id}>
              {o.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Échéance
        <input type="date" required value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
      </label>
    </ActionForm>
  );
}

function ActionsTable({ incident, canManage, onChanged }: { incident: Incident; canManage: boolean; onChanged: () => void }) {
  const me = useMe();
  const [completing, setCompleting] = useState<CorrectiveAction | null>(null);
  const [deciding, setDeciding] = useState<{ action: CorrectiveAction; kind: "REOPEN" | "CANCEL" } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const actions = incident.actions ?? [];
  const canComplete = can(me.grants, "hse.action.complete", incident.site_id);
  async function decide(a: CorrectiveAction, body: Schemas["ActionDecisionIn"]) {
    await call("post", "/hse/corrective-actions/{hse_corrective_action_id}/decision", {
      path: { hse_corrective_action_id: a.hse_corrective_action_id },
      ifMatch: `"${a.row_version}"`,
      body,
    });
    setDeciding(null);
    onChanged();
  }
  if (actions.length === 0) return <p className="muted">Aucune action corrective.</p>;
  return (
    <>
      {error !== null && <ErrorMessage error={error} />}
      {completing && (
        <CompleteActionForm
          action={completing}
          onCancel={() => setCompleting(null)}
          onDone={() => {
            setCompleting(null);
            onChanged();
          }}
        />
      )}
      {deciding && (
        <ActionReasonForm
          title={deciding.kind === "REOPEN" ? "Rouvrir l'action (vérification non concluante)" : "Annuler l'action"}
          onCancel={() => setDeciding(null)}
          onSubmit={(r) => decide(deciding.action, { action: deciding.kind, reason_code: r })}
        />
      )}
      <table>
        <thead>
          <tr>
            <th scope="col">Action</th>
            <th scope="col">Responsable</th>
            <th scope="col">Échéance</th>
            <th scope="col">Statut</th>
            <th scope="col">
              Opérations
            </th>
          </tr>
        </thead>
        <tbody>
          {actions.map((a) => (
            <tr key={a.hse_corrective_action_id}>
              <td>
                {a.title}
                {a.completion_note && <div className="small muted">Réalisation : {a.completion_note}</div>}
              </td>
              <td>{a.owner_name ?? "—"}</td>
              <td>
                {formatDate(a.due_date)}
                {a.overdue && <div className="warn-text small">En retard</div>}
              </td>
              <td>
                <Badge tone={HSE_ACTION_TONE[a.status] ?? "neutral"}>{label(HSE_ACTION_STATUS, a.status)}</Badge>
                {a.status_reason && <div className="small muted">{label(HSE_ACTION_REASONS, a.status_reason)}</div>}
              </td>
              <td className="row">
                {canComplete && a.status === "OPEN" && a.owner_user_id === me.user_account_id && (
                  <button type="button" className="primary" onClick={() => setCompleting(a)}>
                    Déclarer réalisée
                  </button>
                )}
                {canManage && a.status === "DONE" && (
                  <>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => {
                        setError(null);
                        decide(a, { action: "VERIFY" }).catch(setError);
                      }}
                    >
                      Vérifier
                    </button>
                    <button type="button" onClick={() => setDeciding({ action: a, kind: "REOPEN" })}>
                      Rouvrir
                    </button>
                  </>
                )}
                {canManage && (a.status === "OPEN" || a.status === "DONE") && (
                  <button type="button" onClick={() => setDeciding({ action: a, kind: "CANCEL" })}>
                    Annuler
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function CompleteActionForm({ action, onCancel, onDone }: { action: CorrectiveAction; onCancel: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  return (
    <ActionForm
      title={`Déclarer réalisée : ${action.title}`}
      submitLabel="Déclarer réalisée"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/hse/corrective-actions/{hse_corrective_action_id}/complete", {
          path: { hse_corrective_action_id: action.hse_corrective_action_id },
          ifMatch: `"${action.row_version}"`,
          body: { completion_note: note.trim() },
        })
      }
    >
      <label>
        Ce qui a été fait
        <textarea required minLength={10} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function ActionReasonForm({
  title,
  onCancel,
  onSubmit,
}: {
  title: string;
  onCancel: () => void;
  onSubmit: (reason: ActionReason) => Promise<unknown>;
}) {
  const [reason, setReason] = useState("INCOMPLETE");
  return (
    <ActionForm title={title} submitLabel="Confirmer" onCancel={onCancel} onSubmit={() => onSubmit(reason as ActionReason)}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          <Options map={HSE_ACTION_REASONS} />
        </select>
      </label>
    </ActionForm>
  );
}
