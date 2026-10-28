import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm, Fact, Options } from "../components/forms";
import {
  label,
  SYMPTOMS,
  WORK_ORDER_EVENTS,
  WORK_ORDER_PRIORITY,
  WORK_ORDER_REASONS,
  WORK_ORDER_STATUS,
  WORK_ORDER_TONE,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type WorkOrder = Schemas["WorkOrderOut"];
type Status = WorkOrder["status"];
type Decision = Schemas["WorkOrderDecision"]["action"];
type Progress = Schemas["WorkOrderProgress"]["action"];
type Reason = NonNullable<Schemas["WorkOrderDecision"]["reason_code"]>;
type Symptom = Schemas["WorkOrderCreate"]["symptom_code"];
type Priority = NonNullable<Schemas["WorkOrderCreate"]["priority"]>;
const PAGE_SIZE = 50;

function formatMinutes(total: number): string {
  if (!total) return "—";
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

/** Atelier (US-3.01, US-3.06) : ordres de travail du site, signalement de panne. */
export function WorkshopPage() {
  const me = useMe();
  const { siteId, sites, timezoneOf } = useSites();
  const [status, setStatus] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [page, setPage] = useState(1);
  const [reporting, setReporting] = useState(false);
  const orders = useQuery({
    queryKey: ["work-orders", siteId, status, openOnly, page],
    queryFn: () =>
      read("/work-orders", {
        query: {
          site_id: siteId,
          status: (status || null) as Status | null,
          open_only: openOnly,
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = orders.data?.items ?? [];
  return (
    <section>
      <div className="page-head">
        <h1>Atelier</h1>
        {can(me.grants, "maintenance.work_order.request", siteId) && !reporting && (
          <button type="button" className="primary" onClick={() => setReporting(true)}>
            Signaler une panne
          </button>
        )}
      </div>
      {reporting && <ReportForm onClose={() => setReporting(false)} />}
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
            <Options map={WORK_ORDER_STATUS} empty="Tous" />
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
      <DataState loading={orders.isLoading} error={orders.error} empty={items.length === 0} emptyText="Aucun ordre de travail.">
        <table>
          <thead>
            <tr>
              <th scope="col">OT</th>
              <th scope="col">Véhicule</th>
              <th scope="col">Panne</th>
              <th scope="col">Priorité</th>
              <th scope="col">Mécanicien</th>
              <th scope="col">Remise en service prévue</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.work_order_id}>
                <td>
                  <Link to={`/atelier/${o.work_order_id}`}>{o.reference}</Link>
                  <div className="small muted">
                    {siteCode.get(o.site_id)} — {formatDateTime(o.reported_at, timezoneOf(o.site_id))}
                  </div>
                </td>
                <td>
                  <Link to={`/vehicules/${o.vehicle_id}`}>{o.vehicle_fleet_number}</Link>
                  {o.immobilize && <div className="warn-text small">Immobilisé</div>}
                </td>
                <td>{label(SYMPTOMS, o.symptom_code)}</td>
                <td>{label(WORK_ORDER_PRIORITY, o.priority)}</td>
                <td>{o.assigned_name ?? "—"}</td>
                <td>{o.expected_ready_at ? formatDateTime(o.expected_ready_at, timezoneOf(o.site_id)) : "—"}</td>
                <td>
                  <Badge tone={WORK_ORDER_TONE[o.status] ?? "neutral"}>{label(WORK_ORDER_STATUS, o.status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={orders.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function ReportForm({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { siteId } = useSites();
  const vehicles = useQuery({
    queryKey: ["vehicles", "workshop", siteId],
    queryFn: () => read("/vehicles", { query: { site_id: siteId, page_size: 200 } }),
  });
  const [form, setForm] = useState({
    vehicle_id: "",
    symptom_code: "ENGINE",
    priority: "NORMAL",
    description: "",
    immobilize: false,
  });
  return (
    <ActionForm
      title="Signaler une panne"
      submitLabel="Enregistrer le signalement"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/work-orders", {
          body: {
            vehicle_id: form.vehicle_id,
            symptom_code: form.symptom_code as Symptom,
            priority: form.priority as Priority,
            description: form.description.trim() || null,
            immobilize: form.immobilize,
          },
        });
        void queryClient.invalidateQueries({ queryKey: ["work-orders"] });
        navigate(`/atelier/${data.work_order_id}`);
      }}
    >
      <label>
        Véhicule
        <select required value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}>
          <option value="">— Choisir —</option>
          {(vehicles.data?.items ?? []).map((v) => (
            <option key={v.vehicle_id} value={v.vehicle_id}>
              {v.fleet_number}
            </option>
          ))}
        </select>
      </label>
      <label>
        Type de panne
        <select value={form.symptom_code} onChange={(e) => setForm({ ...form, symptom_code: e.target.value })}>
          <Options map={SYMPTOMS} />
        </select>
      </label>
      <label>
        Priorité
        <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
          <Options map={WORK_ORDER_PRIORITY} />
        </select>
      </label>
      <label>
        Description (constat technique)
        <textarea maxLength={2000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={form.immobilize} onChange={(e) => setForm({ ...form, immobilize: e.target.checked })} />
        Panne bloquante : immobiliser le véhicule (sa mission en cours est suspendue)
      </label>
      <p className="muted small">Décrivez la panne, sans nom de personne ni donnée personnelle.</p>
    </ActionForm>
  );
}

type Panel = "approve" | "reject" | "assign" | "cancel" | "qc_fail" | "await" | null;

/** Fiche d'un ordre de travail : actions selon le rôle et l'état, compte rendu, temps passé. */
export function WorkOrderPage() {
  const { workOrderId = "" } = useParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<unknown>(null);
  const order = useQuery({
    queryKey: ["work-order", workOrderId],
    queryFn: () => call("get", "/work-orders/{work_order_id}", { path: { work_order_id: workOrderId } }),
  });
  const o = order.data?.data;
  const etag = order.data?.etag ?? null;
  const tz = timezoneOf(o?.site_id);
  const canManage = o ? can(me.grants, "maintenance.work_order.manage", o.site_id) : false;
  const canExecute = o ? can(me.grants, "maintenance.work_order.execute", o.site_id) : false;
  const refresh = async () => {
    setPanel(null);
    await queryClient.invalidateQueries({ queryKey: ["work-order", workOrderId] });
    void queryClient.invalidateQueries({ queryKey: ["work-orders"] });
  };
  async function decide(action: Decision, extra: Partial<Schemas["WorkOrderDecision"]> = {}) {
    await call("post", "/work-orders/{work_order_id}/decision", {
      path: { work_order_id: workOrderId },
      ifMatch: etag,
      body: { action, ...extra },
    });
    await refresh();
  }
  async function act(action: Progress, extra: Partial<Schemas["WorkOrderProgress"]> = {}) {
    await call("post", "/work-orders/{work_order_id}/progress", {
      path: { work_order_id: workOrderId },
      ifMatch: etag,
      body: { action, ...extra },
    });
    await refresh();
  }
  const run = (fn: () => Promise<unknown>) => {
    setError(null);
    fn().catch(setError);
  };

  return (
    <section>
      <Link className="back" to="/atelier">
        ← Atelier
      </Link>
      <DataState loading={order.isLoading} error={order.error} empty={!o}>
        {o && (
          <>
            <div className="page-head">
              <h1>
                {o.reference} — {o.vehicle_fleet_number}{" "}
                <Badge tone={WORK_ORDER_TONE[o.status] ?? "neutral"}>{label(WORK_ORDER_STATUS, o.status)}</Badge>
              </h1>
            </div>
            <div className="toolbar">
              {canManage && o.status === "REQUESTED" && (
                <>
                  <button type="button" className="primary" onClick={() => setPanel("approve")}>
                    Approuver
                  </button>
                  <button type="button" onClick={() => setPanel("reject")}>
                    Rejeter
                  </button>
                </>
              )}
              {canManage && ["APPROVED", "ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS"].includes(o.status) && (
                <button type="button" className={o.status === "APPROVED" ? "primary" : undefined} onClick={() => setPanel("assign")}>
                  {o.assigned_to ? "Réassigner" : "Assigner un mécanicien"}
                </button>
              )}
              {canExecute && o.status === "ASSIGNED" && (
                <button type="button" className="primary" onClick={() => run(() => act("START"))}>
                  Démarrer l'intervention
                </button>
              )}
              {canExecute && o.status === "IN_PROGRESS" && (
                <button type="button" onClick={() => setPanel("await")}>
                  En attente de pièces
                </button>
              )}
              {canExecute && o.status === "AWAITING_PARTS" && (
                <button type="button" className="primary" onClick={() => run(() => act("RESUME"))}>
                  Reprendre
                </button>
              )}
              {canManage && o.status === "QUALITY_CHECK" && (
                <>
                  <button type="button" className="primary" onClick={() => run(() => decide("QC_PASS"))}>
                    Contrôle conforme : remettre en service
                  </button>
                  <button type="button" onClick={() => setPanel("qc_fail")}>
                    Contrôle non conforme
                  </button>
                </>
              )}
              {canManage && ["REQUESTED", "APPROVED", "ASSIGNED"].includes(o.status) && (
                <button type="button" onClick={() => setPanel("cancel")}>
                  Annuler l'OT
                </button>
              )}
            </div>
            {error !== null && <ErrorMessage error={error} />}
            {panel === "approve" && (
              <ApproveForm timeZone={tz} onCancel={() => setPanel(null)} onSubmit={(ready) => decide("APPROVE", { expected_ready_at: ready })} />
            )}
            {panel === "assign" && (
              <AssignForm order={o} timeZone={tz} onCancel={() => setPanel(null)} onSubmit={(who, ready) => decide("ASSIGN", { assigned_to: who, expected_ready_at: ready })} />
            )}
            {panel === "reject" && <ReasonForm title="Rejeter la demande" submitLabel="Rejeter" onCancel={() => setPanel(null)} onSubmit={(r) => decide("REJECT", { reason_code: r })} />}
            {panel === "cancel" && <ReasonForm title="Annuler l'ordre de travail" submitLabel="Annuler l'OT" danger onCancel={() => setPanel(null)} onSubmit={(r) => decide("CANCEL", { reason_code: r })} />}
            {panel === "qc_fail" && <ReasonForm title="Contrôle non conforme" submitLabel="Renvoyer à l'intervention" onCancel={() => setPanel(null)} onSubmit={(r) => decide("QC_FAIL", { reason_code: r })} />}
            {panel === "await" && <ReasonForm title="Mettre en attente de pièces" submitLabel="Mettre en attente" initial="PARTS_ORDERED" onCancel={() => setPanel(null)} onSubmit={(r) => act("AWAIT_PARTS", { reason_code: r })} />}
            <dl className="facts">
              <Fact label="Panne">{label(SYMPTOMS, o.symptom_code)}</Fact>
              <Fact label="Priorité">{label(WORK_ORDER_PRIORITY, o.priority)}</Fact>
              <Fact label="Panne bloquante">{o.immobilize ? "Oui (véhicule immobilisé)" : "Non"}</Fact>
              <Fact label="Signalée le">{formatDateTime(o.reported_at, tz)}</Fact>
              <Fact label="Mécanicien">{o.assigned_name}</Fact>
              <Fact label="Remise en service prévue">{o.expected_ready_at ? formatDateTime(o.expected_ready_at, tz) : null}</Fact>
              <Fact label="Temps passé">{formatMinutes(o.labour_minutes)}</Fact>
              <Fact label="Motif">{o.status_reason ? label(WORK_ORDER_REASONS, o.status_reason) : null}</Fact>
              <Fact label="Description">{o.description}</Fact>
            </dl>
            <Report order={o} canExecute={canExecute} onSave={(fields, submit) => act(submit ? "SUBMIT" : "NOTE", fields)} />
            <Labour order={o} canExecute={canExecute} onDone={() => void refresh()} />
            <h2>Chronologie</h2>
            <ol className="timeline">
              {(o.events ?? []).map((e, i) => (
                <li key={`${e.occurred_at}-${i}`}>
                  <strong>{label(WORK_ORDER_EVENTS, e.event_type)}</strong> — {formatDateTime(e.occurred_at, tz)}
                  {e.actor_name && <span className="muted"> par {e.actor_name}</span>}
                  {e.reason && <span className="muted"> ({label(WORK_ORDER_REASONS, e.reason)})</span>}
                </li>
              ))}
            </ol>
          </>
        )}
      </DataState>
    </section>
  );
}

function ApproveForm({ timeZone, onCancel, onSubmit }: { timeZone: string; onCancel: () => void; onSubmit: (ready: string | null) => Promise<unknown> }) {
  const [ready, setReady] = useState("");
  return (
    <ActionForm title="Approuver la demande" submitLabel="Approuver" onCancel={onCancel} onSubmit={() => onSubmit(ready ? zonedInputToUtc(ready, timeZone).toISOString() : null)}>
      <label>
        Remise en service prévue (facultatif, heure du site)
        <input type="datetime-local" value={ready} min={utcToZonedInput(new Date(), timeZone)} onChange={(e) => setReady(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function AssignForm({
  order,
  timeZone,
  onCancel,
  onSubmit,
}: {
  order: WorkOrder;
  timeZone: string;
  onCancel: () => void;
  onSubmit: (who: string, ready: string | null) => Promise<unknown>;
}) {
  const mechanics = useQuery({
    queryKey: ["maintenance-mechanics", order.site_id],
    queryFn: () => read("/maintenance-mechanics", { query: { site_id: order.site_id } }),
  });
  const [who, setWho] = useState(order.assigned_to ?? "");
  const [ready, setReady] = useState("");
  return (
    <ActionForm
      title="Assigner un mécanicien"
      submitLabel="Assigner"
      onCancel={onCancel}
      onSubmit={() => onSubmit(who, ready ? zonedInputToUtc(ready, timeZone).toISOString() : null)}
    >
      <label>
        Mécanicien
        <select required value={who} onChange={(e) => setWho(e.target.value)}>
          <option value="">— Choisir —</option>
          {(mechanics.data ?? []).map((m) => (
            <option key={m.user_account_id} value={m.user_account_id}>
              {m.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Remise en service prévue (facultatif, heure du site)
        <input type="datetime-local" value={ready} onChange={(e) => setReady(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function ReasonForm({
  title,
  submitLabel,
  danger,
  initial = "OTHER",
  onCancel,
  onSubmit,
}: {
  title: string;
  submitLabel: string;
  danger?: boolean;
  initial?: Reason;
  onCancel: () => void;
  onSubmit: (reason: Reason) => Promise<unknown>;
}) {
  const [reason, setReason] = useState<Reason>(initial);
  return (
    <ActionForm title={title} submitLabel={submitLabel} danger={danger} onCancel={onCancel} onSubmit={() => onSubmit(reason)}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value as Reason)}>
          <Options map={WORK_ORDER_REASONS} />
        </select>
      </label>
    </ActionForm>
  );
}

function Report({
  order,
  canExecute,
  onSave,
}: {
  order: WorkOrder;
  canExecute: boolean;
  onSave: (fields: { diagnosis: string; work_done: string; parts_note: string }, submit: boolean) => Promise<unknown>;
}) {
  const editable = canExecute && ["ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS", "QUALITY_CHECK"].includes(order.status);
  const [form, setForm] = useState({
    diagnosis: order.diagnosis ?? "",
    work_done: order.work_done ?? "",
    parts_note: order.parts_note ?? "",
  });
  if (!editable) {
    return (
      <>
        <h2>Compte rendu</h2>
        <dl className="facts">
          <Fact label="Diagnostic">{order.diagnosis}</Fact>
          <Fact label="Travaux réalisés">{order.work_done}</Fact>
          <Fact label="Pièces">{order.parts_note}</Fact>
        </dl>
      </>
    );
  }
  return (
    <ActionForm
      title="Compte rendu d'intervention"
      submitLabel={order.status === "IN_PROGRESS" ? "Travaux terminés : passer au contrôle" : "Enregistrer le compte rendu"}
      onSubmit={() => onSave(form, order.status === "IN_PROGRESS")}
    >
      <label>
        Diagnostic
        <textarea maxLength={4000} value={form.diagnosis} onChange={(e) => setForm({ ...form, diagnosis: e.target.value })} />
      </label>
      <label>
        Travaux réalisés
        <textarea maxLength={4000} value={form.work_done} onChange={(e) => setForm({ ...form, work_done: e.target.value })} />
      </label>
      <label>
        Pièces utilisées ou à commander
        <textarea maxLength={2000} value={form.parts_note} onChange={(e) => setForm({ ...form, parts_note: e.target.value })} />
      </label>
      <p className="muted small">La remise en service sera validée par le chef d'atelier ou l'exploitation, pas par vous.</p>
    </ActionForm>
  );
}

function Labour({ order, canExecute, onDone }: { order: WorkOrder; canExecute: boolean; onDone: () => void }) {
  const { timezoneOf } = useSites();
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ minutes: "", performed_on: utcToZonedInput(new Date(), timezoneOf(order.site_id)).slice(0, 10), note: "" });
  const open = ["ASSIGNED", "IN_PROGRESS", "AWAITING_PARTS", "QUALITY_CHECK"].includes(order.status);
  return (
    <>
      <div className="page-head">
        <h2>Temps passé</h2>
        {canExecute && open && !adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Saisir du temps
          </button>
        )}
      </div>
      {adding && (
        <ActionForm
          title="Saisir du temps"
          submitLabel="Enregistrer"
          onCancel={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            onDone();
          }}
          onSubmit={() =>
            call("post", "/work-orders/{work_order_id}/labour", {
              path: { work_order_id: order.work_order_id },
              body: { minutes: Number(form.minutes), performed_on: form.performed_on, note: form.note.trim() || null },
            })
          }
        >
          <label>
            Durée (minutes)
            <input type="number" required min={1} max={960} value={form.minutes} onChange={(e) => setForm({ ...form, minutes: e.target.value })} />
          </label>
          <label>
            Jour
            <input type="date" required value={form.performed_on} onChange={(e) => setForm({ ...form, performed_on: e.target.value })} />
          </label>
          <label>
            Note (facultative)
            <input maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </label>
        </ActionForm>
      )}
      <DataState loading={false} error={null} empty={(order.labour ?? []).length === 0} emptyText="Aucun temps saisi.">
        <table>
          <thead>
            <tr>
              <th scope="col">Jour</th>
              <th scope="col">Mécanicien</th>
              <th scope="col">Durée</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {(order.labour ?? []).map((l) => (
              <tr key={l.work_order_labour_id}>
                <td>{l.performed_on}</td>
                <td>{l.mechanic_name ?? "—"}</td>
                <td>{formatMinutes(l.minutes)}</td>
                <td>{l.note ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}
