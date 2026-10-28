import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import {
  DEGRADED_REASONS,
  formatDuration,
  formatTonnes,
  label,
  VOID_REASONS,
  WEIGHING_SOURCE,
  WEIGHING_STATUS,
  WEIGHING_TONE,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Ticket = Schemas["WeighingOut"];
type Fields = Omit<Schemas["WeighingCreate"], "rotation_id">;
type VoidReason = Schemas["WeighingVoid"]["reason_code"];
type DegradedReason = NonNullable<Fields["degraded_reason"]>;
const PAGE_SIZE = 50;

/**
 * Champs d'une pesée (saisie ou correction). Le poids net n'est jamais saisi : il est calculé par le
 * serveur (brut − tare) ; l'aperçu ci-dessous n'est qu'une aide.
 */
export function WeighingForm({
  siteId,
  title,
  submitLabel,
  initial,
  children,
  onSubmit,
  onCancel,
  onDone,
}: {
  siteId: string;
  title: string;
  submitLabel: string;
  initial?: Ticket;
  children?: React.ReactNode;
  onSubmit: (fields: Fields) => Promise<unknown>;
  onCancel: () => void;
  onDone?: () => void;
}) {
  const { timezoneOf } = useSites();
  const tz = timezoneOf(siteId);
  const bridges = useQuery({
    queryKey: ["site-locations", siteId],
    queryFn: () => read("/site-locations", { query: { site_id: siteId } }),
  });
  const weighbridges = (bridges.data ?? []).filter((p) => p.kind === "WEIGHBRIDGE");
  const [form, setForm] = useState({
    weighbridge_location_id: initial?.weighbridge_location_id ?? "",
    ticket_number: initial?.ticket_number ?? "",
    source: initial?.source ?? "WEIGHBRIDGE",
    degraded_reason: initial?.degraded_reason ?? "WEIGHBRIDGE_DOWN",
    weighed_at: utcToZonedInput(initial ? new Date(initial.weighed_at) : new Date(), tz),
    gross_kg: initial ? String(initial.gross_kg) : "",
    tare_kg: initial ? String(initial.tare_kg) : "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const degraded = form.source === "MANUAL_DEGRADED";
  const net = Number(form.gross_kg) - Number(form.tare_kg);
  return (
    <ActionForm
      title={title}
      submitLabel={submitLabel}
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        onSubmit({
          weighbridge_location_id: form.weighbridge_location_id,
          ticket_number: form.ticket_number.trim(),
          source: form.source as Fields["source"],
          degraded_reason: degraded ? (form.degraded_reason as DegradedReason) : null,
          weighed_at: zonedInputToUtc(form.weighed_at, tz).toISOString(),
          gross_kg: Number(form.gross_kg),
          tare_kg: Number(form.tare_kg),
        })
      }
    >
      <label>
        Pont-bascule
        <select required value={form.weighbridge_location_id} onChange={set("weighbridge_location_id")}>
          <option value="">— Choisir —</option>
          {weighbridges.map((p) => (
            <option key={p.site_location_id} value={p.site_location_id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {bridges.isSuccess && weighbridges.length === 0 && (
        <p className="warn-text small">
          Aucun pont-bascule sur ce site : déclarez-en un dans Administration › Lieux et matières.
        </p>
      )}
      <label>
        Numéro du ticket
        <input required pattern="[A-Za-z0-9/_\-]{1,40}" maxLength={40} value={form.ticket_number} onChange={set("ticket_number")} />
      </label>
      <label>
        Source
        <select value={form.source} onChange={set("source")}>
          <Options map={WEIGHING_SOURCE} />
        </select>
      </label>
      {degraded && (
        <label>
          Motif de la saisie manuelle
          <select value={form.degraded_reason} onChange={set("degraded_reason")}>
            <Options map={DEGRADED_REASONS} />
          </select>
        </label>
      )}
      <label>
        Heure de pesée (heure du site)
        <input type="datetime-local" required value={form.weighed_at} onChange={set("weighed_at")} />
      </label>
      <label>
        Poids brut (kg)
        <input type="number" required min={1} max={500000} step={1} value={form.gross_kg} onChange={set("gross_kg")} />
      </label>
      <label>
        Tare (kg)
        <input type="number" required min={1} max={500000} step={1} value={form.tare_kg} onChange={set("tare_kg")} />
      </label>
      <p className="muted small" aria-live="polite">
        Net : {net > 0 ? formatTonnes(net) : "—"} (calculé par le serveur).
        {degraded && " Une saisie manuelle doit être approuvée par une autre personne avant de compter comme mesurée."}
      </p>
      {children}
    </ActionForm>
  );
}

type Panel = { kind: "void" | "correct"; ticket: Ticket } | null;

/** Liste des pesées avec approbation, annulation et correction (US-2.05, US-2.06). */
export function WeighingsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, sites, timezoneOf } = useSites();
  const [status, setStatus] = useState("");
  const [overloadOnly, setOverloadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<unknown>(null);
  const tickets = useQuery({
    queryKey: ["weighing-tickets", siteId, status, overloadOnly, page],
    queryFn: () =>
      read("/weighing-tickets", {
        query: {
          site_id: siteId,
          status: (status || null) as Ticket["status"] | null,
          overload: overloadOnly ? true : null,
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const refresh = () => {
    setPanel(null);
    void queryClient.invalidateQueries({ queryKey: ["weighing-tickets"] });
    void queryClient.invalidateQueries({ queryKey: ["dispatch-indicators"] });
  };
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = tickets.data?.items ?? [];

  async function approve(ticket: Ticket) {
    setError(null);
    try {
      await call("post", "/weighing-tickets/{weighing_ticket_id}/approve", {
        path: { weighing_ticket_id: ticket.weighing_ticket_id },
        body: {},
      });
      refresh();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>Pesées</h1>
      </div>
      <p className="muted small">
        Seules les pesées valides font foi pour le tonnage. Une saisie manuelle (pont en panne) reste « à approuver » tant
        qu'une autre personne ne l'a pas validée. La saisie se fait depuis la fiche de la mission.
      </p>
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
            <Options map={WEIGHING_STATUS} empty="Tous" />
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={overloadOnly}
            onChange={(e) => {
              setOverloadOnly(e.target.checked);
              setPage(1);
            }}
          />
          Surcharges seulement
        </label>
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {panel?.kind === "void" && <VoidForm ticket={panel.ticket} onCancel={() => setPanel(null)} onDone={refresh} />}
      {panel?.kind === "correct" && (
        <CorrectForm ticket={panel.ticket} onCancel={() => setPanel(null)} onDone={refresh} />
      )}
      <DataState loading={tickets.isLoading} error={tickets.error} empty={items.length === 0} emptyText="Aucune pesée.">
        <table>
          <thead>
            <tr>
              <th scope="col">Pesée le</th>
              <th scope="col">Ticket</th>
              <th scope="col">Véhicule</th>
              <th scope="col">Matière</th>
              <th scope="col">Net</th>
              <th scope="col">Source</th>
              <th scope="col">Statut</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.weighing_ticket_id}>
                <td>
                  {formatDateTime(t.weighed_at, timezoneOf(t.site_id))}
                  <div className="small muted">{siteCode.get(t.site_id)}</div>
                </td>
                <td>
                  {t.ticket_number}
                  <div className="small muted">{t.weighbridge_name}</div>
                </td>
                <td>{t.vehicle_fleet_number}</td>
                <td>
                  <Link to={`/missions/${t.mission_id}`}>{t.material_name}</Link>
                  <div className="small muted">Rotation {t.rotation_sequence}</div>
                </td>
                <td>
                  {formatTonnes(t.net_kg)}
                  {t.overload && <div className="warn-text small">Surcharge (capacité {formatTonnes(t.rated_payload_kg)})</div>}
                </td>
                <td>
                  {label(WEIGHING_SOURCE, t.source)}
                  {t.degraded_reason && <div className="small muted">{label(DEGRADED_REASONS, t.degraded_reason)}</div>}
                </td>
                <td>
                  <Badge tone={WEIGHING_TONE[t.status] ?? "neutral"}>{label(WEIGHING_STATUS, t.status)}</Badge>
                  {t.replaces_ticket_id && <div className="small muted">Corrige une pesée annulée</div>}
                </td>
                <td>
                  <div className="row">
                    {t.status === "PENDING_APPROVAL" && can(me.grants, "dispatch.weighing.approve", t.site_id) && (
                      <button type="button" onClick={() => void approve(t)}>
                        Approuver
                      </button>
                    )}
                    {t.status !== "VOIDED" && can(me.grants, "dispatch.weighing.correct", t.site_id) && (
                      <>
                        <button type="button" onClick={() => setPanel({ kind: "correct", ticket: t })}>
                          Corriger
                        </button>
                        <button type="button" onClick={() => setPanel({ kind: "void", ticket: t })}>
                          Annuler
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={tickets.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function VoidForm({ ticket, onCancel, onDone }: { ticket: Ticket; onCancel: () => void; onDone: () => void }) {
  const [reason, setReason] = useState<VoidReason>("ENTRY_ERROR");
  return (
    <ActionForm
      title={`Annuler la pesée ${ticket.ticket_number}`}
      submitLabel="Annuler la pesée"
      danger
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/weighing-tickets/{weighing_ticket_id}/void", {
          path: { weighing_ticket_id: ticket.weighing_ticket_id },
          body: { reason_code: reason },
        })
      }
    >
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value as VoidReason)}>
          <Options map={VOID_REASONS} />
        </select>
      </label>
      <p className="muted small">La pesée reste consultable avec son motif d'annulation ; rien n'est effacé.</p>
    </ActionForm>
  );
}

function CorrectForm({ ticket, onCancel, onDone }: { ticket: Ticket; onCancel: () => void; onDone: () => void }) {
  const [reason, setReason] = useState<VoidReason>("ENTRY_ERROR");
  return (
    <WeighingForm
      siteId={ticket.site_id}
      title={`Corriger la pesée ${ticket.ticket_number}`}
      submitLabel="Enregistrer la correction"
      initial={ticket}
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={(fields) =>
        call("post", "/weighing-tickets/{weighing_ticket_id}/correct", {
          path: { weighing_ticket_id: ticket.weighing_ticket_id },
          body: { ...fields, reason_code: reason },
        })
      }
    >
      <label>
        Motif de la correction
        <select value={reason} onChange={(e) => setReason(e.target.value as VoidReason)}>
          <Options map={VOID_REASONS} />
        </select>
      </label>
    </WeighingForm>
  );
}

function dayInput(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Indicateurs par site et matière (US-2.08) : mesuré, en attente et estimé toujours séparés (RM-072). */
export function IndicatorsPage() {
  const { siteId, sites, timezoneOf } = useSites();
  const today = new Date();
  const [from, setFrom] = useState(dayInput(new Date(today.getTime() - 7 * 86_400_000)));
  const [to, setTo] = useState(dayInput(today));
  const tz = timezoneOf(siteId);
  const start = zonedInputToUtc(`${from}T00:00`, tz).toISOString();
  // Fin incluse : jusqu'au lendemain 0 h, heure du site.
  const end = new Date(zonedInputToUtc(`${to}T00:00`, tz).getTime() + 86_400_000).toISOString();
  const indicators = useQuery({
    queryKey: ["dispatch-indicators", siteId, start, end],
    queryFn: () => read("/dispatch-indicators", { query: { site_id: siteId, period_start: start, period_end: end } }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const rows = indicators.data?.rows ?? [];
  return (
    <section>
      <div className="page-head">
        <h1>Indicateurs de transport</h1>
      </div>
      <div className="filters">
        <label>
          Du
          <input type="date" required value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label>
          Au (inclus)
          <input type="date" required value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <p className="muted small">
        Rotations terminées sur la période (92 jours au plus). Le tonnage <strong>mesuré</strong> vient des seules pesées
        valides ; les saisies manuelles <strong>à approuver</strong> et l'<strong>estimation</strong> (capacité nominale ×
        rotations non pesées) sont affichées à part et ne s'additionnent jamais au mesuré. Le GPS n'est jamais une source
        de tonnage.
      </p>
      <DataState
        loading={indicators.isLoading}
        error={indicators.error}
        empty={rows.length === 0}
        emptyText="Aucune rotation terminée sur cette période."
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">Matière</th>
              <th scope="col">Missions terminées</th>
              <th scope="col">Rotations</th>
              <th scope="col">Cycle moyen</th>
              <th scope="col">Mesuré</th>
              <th scope="col">À approuver</th>
              <th scope="col">Estimé</th>
              <th scope="col">À vérifier</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.site_id}-${r.material_id}`}>
                <td>{siteCode.get(r.site_id)}</td>
                <td>{r.material_name}</td>
                <td>{r.missions_completed}</td>
                <td>{r.rotations_completed}</td>
                <td>{formatDuration(r.avg_cycle_seconds)}</td>
                <td>
                  {formatTonnes(r.measured_net_kg)}
                  <div className="small muted">{r.measured_rotations} rotation(s) pesée(s)</div>
                </td>
                <td>
                  {formatTonnes(r.pending_net_kg)}
                  <div className="small muted">{r.pending_rotations} rotation(s)</div>
                </td>
                <td>
                  <em>{formatTonnes(r.estimated_kg)} (estimé)</em>
                  <div className="small muted">
                    {r.estimated_rotations} rotation(s)
                    {r.rotations_without_estimate > 0 && `, ${r.rotations_without_estimate} sans capacité connue`}
                  </div>
                </td>
                <td>
                  {r.short_cycles > 0 && <div className="warn-text small">{r.short_cycles} cycle(s) anormalement court(s)</div>}
                  {r.overload_tickets > 0 && <div className="warn-text small">{r.overload_tickets} surcharge(s)</div>}
                  {r.short_cycles === 0 && r.overload_tickets === 0 && "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}
