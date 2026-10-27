import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { call, read, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import {
  ASSIGNMENT_STATUS,
  CANCEL_REASONS,
  END_REASONS,
  ISSUES,
  label,
  SUSPEND_REASONS,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Assignment = Schemas["AssignmentOut"];
type Action = "activate" | "suspend" | "resume" | "complete" | "cancel";

const PAGE_SIZE = 50;
const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  PLANNED: "neutral",
  ACTIVE: "ok",
  SUSPENDED: "warn",
  COMPLETED: "neutral",
  CANCELLED: "neutral",
};
const ACTIONS: Record<string, { action: Action; text: string; reasons?: Record<string, string> }[]> = {
  PLANNED: [
    { action: "activate", text: "Prise de poste" },
    { action: "cancel", text: "Annuler", reasons: CANCEL_REASONS },
  ],
  ACTIVE: [
    { action: "suspend", text: "Suspendre", reasons: SUSPEND_REASONS },
    { action: "complete", text: "Clôturer", reasons: END_REASONS },
  ],
  SUSPENDED: [
    { action: "resume", text: "Reprendre" },
    { action: "complete", text: "Clôturer", reasons: END_REASONS },
  ],
};

function issueText(issue: { code: string; date?: string | null }): string {
  return `${label(ISSUES, issue.code)}${issue.date ? ` (${formatDate(issue.date)})` : ""}`;
}

export function AssignmentsPage() {
  const me = useMe();
  const { siteId, sites, timezoneOf } = useSites();
  const [status, setStatus] = useState("");
  const [compliance, setCompliance] = useState("");
  const [page, setPage] = useState(1);
  const canCreate = can(me.grants, "assignment.vehicle_assignment.create", siteId);
  const canAct = can(me.grants, "assignment.vehicle_assignment.update", siteId) || can(me.grants, "assignment.vehicle_assignment.end", siteId);
  const list = useQuery({
    queryKey: ["assignments", siteId, status, compliance, page],
    queryFn: () =>
      read("/vehicle-assignments", {
        query: {
          site_id: siteId,
          status: (status || null) as Assignment["status"] | null,
          compliance: (compliance || null) as "COMPLIANT" | "NON_COMPLIANT" | null,
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = list.data?.items ?? [];

  return (
    <section>
      <h1>Affectations conducteur ↔ véhicule</h1>
      {canCreate && <CreateAssignment />}
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
            <option value="">Tous</option>
            {Object.entries(ASSIGNMENT_STATUS).map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label>
          Conformité (affectations actives)
          <select
            value={compliance}
            onChange={(e) => {
              setCompliance(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Toutes</option>
            <option value="NON_COMPLIANT">Non conformes</option>
            <option value="COMPLIANT">Conformes</option>
          </select>
        </label>
      </div>
      <DataState loading={list.isLoading} error={list.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Véhicule</th>
              <th scope="col">Conducteur</th>
              <th scope="col">Site</th>
              <th scope="col">Début</th>
              <th scope="col">Fin</th>
              <th scope="col">Statut</th>
              <th scope="col">Conformité</th>
              {canAct && <th scope="col">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <AssignmentRow
                key={a.vehicle_assignment_id}
                assignment={a}
                site={siteCode.get(a.site_id) ?? "—"}
                timeZone={timezoneOf(a.site_id)}
                canWrite={canAct && (can(me.grants, "assignment.vehicle_assignment.update", a.site_id) || can(me.grants, "assignment.vehicle_assignment.end", a.site_id))}
              />
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={list.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function AssignmentRow({
  assignment: a,
  site,
  timeZone,
  canWrite,
}: {
  assignment: Assignment;
  site: string;
  timeZone: string;
  canWrite: boolean;
}) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<{ action: Action; reasons: Record<string, string> } | null>(null);
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: ({ action, reasonCode }: { action: Action; reasonCode?: string }) =>
      request<Assignment>(`/vehicle-assignments/${a.vehicle_assignment_id}/${action}`, {
        method: "POST",
        ifMatch: `"${a.row_version}"`,
        body: action === "activate" || action === "resume" ? undefined : reasonCode ? { reason_code: reasonCode } : {},
      }),
    onSuccess: () => {
      setPending(null);
      void queryClient.invalidateQueries({ queryKey: ["assignments"] });
    },
  });

  function run(action: Action, reasons?: Record<string, string>) {
    if (reasons) {
      setPending({ action, reasons });
      setReason(Object.keys(reasons)[0] ?? "");
      return;
    }
    mutation.mutate({ action });
  }

  return (
    <>
      <tr>
        <td>{a.vehicle_fleet_number}</td>
        <td>
          {a.driver_display_name}
          <div className="muted small">{a.driver_employee_number}</div>
        </td>
        <td>{site}</td>
        <td>
          {formatDateTime(a.valid_from, timeZone)}
          {a.activation_overdue && <div className="warn-text small">Prise de poste en retard</div>}
        </td>
        <td>
          {formatDateTime(a.valid_to, timeZone)}
          {a.end_overdue && <div className="warn-text small">Fin dépassée</div>}
        </td>
        <td>
          <Badge tone={STATUS_TONE[a.status] ?? "neutral"}>{label(ASSIGNMENT_STATUS, a.status)}</Badge>
        </td>
        <td>
          {a.compliance ? (
            <>
              <Badge tone={a.compliance.status === "COMPLIANT" ? "ok" : "bad"}>
                {a.compliance.status === "COMPLIANT" ? "Conforme" : "Non conforme"}
              </Badge>
              {[...a.compliance.reasons, ...a.compliance.warnings].map((i) => (
                <div key={i.code} className="small">
                  {issueText(i)}
                </div>
              ))}
            </>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        {canWrite && (
          <td className="actions">
            {(ACTIONS[a.status] ?? []).map((item) => (
              <button
                key={item.action}
                type="button"
                disabled={mutation.isPending}
                onClick={() => run(item.action, item.reasons)}
              >
                {item.text}
              </button>
            ))}
          </td>
        )}
      </tr>
      {(pending || mutation.error) && (
        <tr className="subrow">
          <td colSpan={canWrite ? 8 : 7}>
            {pending && (
              <form
                className="inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  mutation.mutate({ action: pending.action, reasonCode: reason });
                }}
              >
                <label>
                  Motif
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>
                    {Object.entries(pending.reasons).map(([code, text]) => (
                      <option key={code} value={code}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" className="primary" disabled={mutation.isPending}>
                  Confirmer
                </button>
                <button type="button" onClick={() => setPending(null)}>
                  Abandonner
                </button>
              </form>
            )}
            {mutation.error && <ErrorMessage error={mutation.error} />}
          </td>
        </tr>
      )}
    </>
  );
}

function CreateAssignment() {
  const queryClient = useQueryClient();
  const { siteId, timezoneOf } = useSites();
  const [open, setOpen] = useState(false);
  const [vehicleId, setVehicleId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [created, setCreated] = useState<Assignment | null>(null);

  const vehicles = useQuery({
    queryKey: ["vehicles", "available", siteId],
    enabled: open,
    queryFn: () =>
      read("/vehicles", { query: { site_id: siteId, status: "AVAILABLE", page_size: 200 } }),
  });
  const vehicle = useMemo(
    () => vehicles.data?.items.find((v) => v.vehicle_id === vehicleId),
    [vehicles.data, vehicleId],
  );
  // Véhicule, conducteur et affectation partagent le même site (D-13) : conducteurs du site du véhicule.
  const drivers = useQuery({
    queryKey: ["drivers", "active", vehicle?.site_id],
    enabled: open && Boolean(vehicle),
    queryFn: () =>
      read("/drivers", { query: { site_id: vehicle?.site_id, status: "ACTIVE", page_size: 200 } }),
  });
  const timeZone = timezoneOf(vehicle?.site_id ?? siteId);

  const mutation = useMutation({
    mutationFn: () =>
      call("post", "/vehicle-assignments", {
        body: {
          vehicle_id: vehicleId,
          driver_id: driverId,
          valid_from: zonedInputToUtc(start, timeZone).toISOString(),
          valid_to: end ? zonedInputToUtc(end, timeZone).toISOString() : null,
        },
      }),
    onSuccess: ({ data }) => {
      setCreated(data);
      setDriverId("");
      void queryClient.invalidateQueries({ queryKey: ["assignments"] });
      void queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!mutation.isPending) mutation.mutate();
  }

  if (!open) {
    return (
      <button
        type="button"
        className="primary"
        onClick={() => {
          setOpen(true);
          setCreated(null);
          setStart(utcToZonedInput(new Date(), timeZone));
        }}
      >
        Nouvelle affectation
      </button>
    );
  }

  return (
    <form className="card form-grid" onSubmit={submit} aria-label="Nouvelle affectation">
      <h2>Nouvelle affectation</h2>
      <label>
        Véhicule disponible
        <select required value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
          <option value="">— Choisir —</option>
          {(vehicles.data?.items ?? []).map((v) => (
            <option key={v.vehicle_id} value={v.vehicle_id}>
              {v.fleet_number}
              {v.registration_number ? ` (${v.registration_number})` : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Conducteur actif du même site
        <select required disabled={!vehicle} value={driverId} onChange={(e) => setDriverId(e.target.value)}>
          <option value="">— Choisir —</option>
          {(drivers.data?.items ?? []).map((d) => (
            <option key={d.driver_id} value={d.driver_id}>
              {d.last_name.toUpperCase()} {d.first_name} — {d.employee_number}
            </option>
          ))}
        </select>
      </label>
      <label>
        Début (heure du site, {timeZone})
        <input type="datetime-local" required value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label>
        Fin prévue (facultative)
        <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
      </label>
      {mutation.error && <ErrorMessage error={mutation.error} />}
      {created && (
        <div className="success" role="status">
          <p>Affectation enregistrée ({label(ASSIGNMENT_STATUS, created.status)}).</p>
          {(created.warnings ?? []).map((w) => (
            <p key={w.code} className="small">
              {issueText(w)}
            </p>
          ))}
        </div>
      )}
      <div className="row">
        {/* Bouton désactivé pendant l'envoi : pas de double soumission (US-1.22 A13). */}
        <button type="submit" className="primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Enregistrement…" : "Affecter"}
        </button>
        <button type="button" onClick={() => setOpen(false)}>
          Fermer
        </button>
      </div>
    </form>
  );
}
