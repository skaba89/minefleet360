import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ActionForm, Fact, intOrNull, Options, orNull } from "../components/forms";
import { ASSIGNMENT_STATUS, FUEL, label, OWNERSHIP, VEHICLE_REASONS, VEHICLE_STATUS } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";
import { Documents, Meters } from "./VehicleRecords";
import { useCategories, VEHICLE_TONE } from "./VehiclesPage";

type Vehicle = Schemas["VehicleOut"];
type VehicleUpdate = Schemas["VehicleUpdate"];
type OperationalStatus = Schemas["VehicleStatusChange"]["status"];
type ReasonCode = NonNullable<Schemas["VehicleStatusChange"]["reason_code"]>;

// Machine à états du serveur (fleet/service.py TRANSITIONS, MODELE_CONCEPTUEL 4.1) : le serveur revalide.
const TRANSITIONS: Record<string, OperationalStatus[]> = {
  AVAILABLE: ["IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"],
  IMMOBILIZED: ["IN_MAINTENANCE", "AVAILABLE", "OUT_OF_SERVICE"],
  IN_MAINTENANCE: ["AVAILABLE", "IMMOBILIZED", "OUT_OF_SERVICE"],
  OUT_OF_SERVICE: ["IN_MAINTENANCE"],
  RETIRED: [],
};
const REASON_REQUIRED = new Set(["IMMOBILIZED", "OUT_OF_SERVICE"]);

type Panel = "edit" | "status" | "retire" | null;

export function VehicleDetailPage() {
  const { vehicleId = "" } = useParams();
  const me = useMe();
  const { sites, timezoneOf } = useSites();
  const [panel, setPanel] = useState<Panel>(null);
  const queryClient = useQueryClient();
  const vehicle = useQuery({
    queryKey: ["vehicle", vehicleId],
    queryFn: () => call("get", "/vehicles/{vehicle_id}", { path: { vehicle_id: vehicleId } }),
  });
  const categories = useCategories();
  const v = vehicle.data?.data;
  const etag = vehicle.data?.etag ?? null;
  const done = () => {
    setPanel(null);
    void queryClient.invalidateQueries({ queryKey: ["vehicle", vehicleId] });
    void queryClient.invalidateQueries({ queryKey: ["vehicle-history", vehicleId] });
    void queryClient.invalidateQueries({ queryKey: ["vehicles"] });
  };

  return (
    <section>
      <Link className="back" to="/vehicules">
        ← Véhicules
      </Link>
      <DataState loading={vehicle.isLoading} error={vehicle.error} empty={!v}>
        {v && (
          <>
            <div className="page-head">
              <h1>
                {v.fleet_number}{" "}
                <Badge tone={VEHICLE_TONE[v.status] ?? "neutral"}>{label(VEHICLE_STATUS, v.status)}</Badge>
              </h1>
            </div>
            <div className="toolbar">
              {v.status !== "RETIRED" && can(me.grants, "fleet.vehicle.update", v.site_id) && (
                <button type="button" onClick={() => setPanel("edit")}>
                  Modifier
                </button>
              )}
              {(TRANSITIONS[v.status] ?? []).length > 0 && can(me.grants, "fleet.vehicle.update_status", v.site_id) && (
                <button type="button" onClick={() => setPanel("status")}>
                  Changer le statut
                </button>
              )}
              {v.status !== "RETIRED" && can(me.grants, "fleet.vehicle.deactivate", v.site_id) && (
                <button type="button" onClick={() => setPanel("retire")}>
                  Réformer
                </button>
              )}
            </div>
            {panel === "edit" && <EditVehicle vehicle={v} etag={etag} onDone={done} onCancel={() => setPanel(null)} />}
            {panel === "status" && (
              <ChangeStatus vehicle={v} etag={etag} onDone={done} onCancel={() => setPanel(null)} />
            )}
            {panel === "retire" && <Retire vehicle={v} etag={etag} onDone={done} onCancel={() => setPanel(null)} />}
            <dl className="facts">
              <Fact label="Site">{sites.find((s) => s.site_id === v.site_id)?.name}</Fact>
              <Fact label="Catégorie">
                {categories.data?.find((c) => c.vehicle_category_id === v.vehicle_category_id)?.label_fr}
              </Fact>
              <Fact label="Immatriculation">{v.registration_number}</Fact>
              <Fact label="N° de série">{v.serial_number}</Fact>
              <Fact label="Marque / modèle">{[v.make, v.model, v.model_year].filter(Boolean).join(" ") || null}</Fact>
              <Fact label="Propriété">{label(OWNERSHIP, v.ownership_type)}</Fact>
              <Fact label="Carburant">{label(FUEL, v.fuel_type)}</Fact>
              <Fact label="Charge utile nominale">
                {v.rated_payload_kg ? `${v.rated_payload_kg.toLocaleString("fr-FR")} kg (constructeur, pas une pesée)` : null}
              </Fact>
              <Fact label="Motif du statut">{v.status_reason_code ? label(VEHICLE_REASONS, v.status_reason_code) : null}</Fact>
              <Fact label="Mise en service">{formatDate(v.commissioned_on)}</Fact>
              <Fact label="Réforme">{v.decommissioned_on ? formatDate(v.decommissioned_on) : null}</Fact>
              <Fact label="Notes">{v.notes}</Fact>
            </dl>
            {can(me.grants, "fleet.meter.read", v.site_id) && (
              <Meters
                vehicle={v}
                category={categories.data?.find((c) => c.vehicle_category_id === v.vehicle_category_id)}
              />
            )}
            {can(me.grants, "fleet.document.read", v.site_id) && <Documents vehicle={v} />}
            <History vehicle={v} timeZone={timezoneOf(v.site_id)} />
          </>
        )}
      </DataState>
    </section>
  );
}

function EditVehicle({
  vehicle: v,
  etag,
  onDone,
  onCancel,
}: {
  vehicle: Vehicle;
  etag: string | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const me = useMe();
  const { sites } = useSites();
  const categories = useCategories();
  const initial = {
    site_id: v.site_id,
    vehicle_category_id: v.vehicle_category_id,
    registration_number: v.registration_number ?? "",
    serial_number: v.serial_number ?? "",
    make: v.make ?? "",
    model: v.model ?? "",
    model_year: v.model_year?.toString() ?? "",
    ownership_type: v.ownership_type,
    fuel_type: v.fuel_type ?? "",
    rated_payload_kg: v.rated_payload_kg?.toString() ?? "",
    commissioned_on: v.commissioned_on ?? "",
    notes: v.notes ?? "",
  };
  const [form, setForm] = useState(initial);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  function changes(): VehicleUpdate {
    const body: Record<string, unknown> = {};
    for (const key of Object.keys(form) as (keyof typeof form)[]) {
      if (form[key] === initial[key]) continue;
      if (key === "model_year" || key === "rated_payload_kg") body[key] = intOrNull(form[key]);
      else if (key === "site_id" || key === "vehicle_category_id" || key === "ownership_type") body[key] = form[key];
      else body[key] = orNull(form[key]);
    }
    return body as VehicleUpdate;
  }

  return (
    <ActionForm
      title="Modifier le véhicule"
      submitLabel="Enregistrer"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("patch", "/vehicles/{vehicle_id}", {
          path: { vehicle_id: v.vehicle_id },
          body: changes(),
          ifMatch: etag,
        })
      }
    >
      <label>
        Site
        <select value={form.site_id} onChange={set("site_id")}>
          {sites
            .filter((s) => s.site_id === v.site_id || (s.status === "ACTIVE" && can(me.grants, "fleet.vehicle.update", s.site_id)))
            .map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.code} — {s.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Catégorie
        <select value={form.vehicle_category_id} onChange={set("vehicle_category_id")}>
          {(categories.data ?? []).map((c) => (
            <option key={c.vehicle_category_id} value={c.vehicle_category_id}>
              {c.label_fr}
            </option>
          ))}
        </select>
      </label>
      <label>
        Immatriculation
        <input maxLength={20} value={form.registration_number} onChange={set("registration_number")} />
      </label>
      <label>
        N° de série
        <input maxLength={60} value={form.serial_number} onChange={set("serial_number")} />
      </label>
      <label>
        Marque
        <input maxLength={60} value={form.make} onChange={set("make")} />
      </label>
      <label>
        Modèle
        <input maxLength={60} value={form.model} onChange={set("model")} />
      </label>
      <label>
        Année
        <input type="number" min={1950} max={2100} value={form.model_year} onChange={set("model_year")} />
      </label>
      <label>
        Propriété
        <select value={form.ownership_type} onChange={set("ownership_type")}>
          <Options map={OWNERSHIP} />
        </select>
      </label>
      <label>
        Carburant
        <select value={form.fuel_type} onChange={set("fuel_type")}>
          <Options map={FUEL} empty="—" />
        </select>
      </label>
      <label>
        Charge utile nominale (kg)
        <input type="number" min={1} value={form.rated_payload_kg} onChange={set("rated_payload_kg")} />
      </label>
      <label>
        Mise en service
        <input type="date" value={form.commissioned_on} onChange={set("commissioned_on")} />
      </label>
      <label>
        Notes (pas de donnée personnelle)
        <textarea maxLength={1000} rows={2} value={form.notes} onChange={set("notes")} />
      </label>
    </ActionForm>
  );
}

function ChangeStatus({
  vehicle: v,
  etag,
  onDone,
  onCancel,
}: {
  vehicle: Vehicle;
  etag: string | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const targets = TRANSITIONS[v.status] ?? [];
  const [status, setStatus] = useState<OperationalStatus>(targets[0] ?? "AVAILABLE");
  const [reason, setReason] = useState("");
  return (
    <ActionForm
      title="Changer le statut"
      submitLabel="Valider le statut"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/vehicles/{vehicle_id}/status", {
          path: { vehicle_id: v.vehicle_id },
          body: { status, reason_code: (orNull(reason) as ReasonCode | null) },
          ifMatch: etag,
        })
      }
    >
      <label>
        Nouveau statut
        <select value={status} onChange={(e) => setStatus(e.target.value as OperationalStatus)}>
          {targets.map((t) => (
            <option key={t} value={t}>
              {label(VEHICLE_STATUS, t)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Motif{REASON_REQUIRED.has(status) ? " (obligatoire)" : ""}
        <select required={REASON_REQUIRED.has(status)} value={reason} onChange={(e) => setReason(e.target.value)}>
          <Options map={VEHICLE_REASONS} empty="—" />
        </select>
      </label>
      <p className="muted small">
        Si le véhicule est affecté, l'affectation est signalée non conforme (ou clôturée, selon la configuration
        de votre société). Pour une réforme, clôturez d'abord ses affectations.
      </p>
    </ActionForm>
  );
}

function Retire({
  vehicle: v,
  etag,
  onDone,
  onCancel,
}: {
  vehicle: Vehicle;
  etag: string | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState<ReasonCode>("END_OF_LIFE");
  return (
    <ActionForm
      title="Réformer le véhicule (définitif)"
      submitLabel="Réformer"
      danger
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/vehicles/{vehicle_id}/retire", {
          path: { vehicle_id: v.vehicle_id },
          body: { reason_code: reason },
          ifMatch: etag,
        })
      }
    >
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value as ReasonCode)}>
          <Options map={VEHICLE_REASONS} />
        </select>
      </label>
      <p className="muted small">
        Un véhicule réformé n'est plus modifiable ni affectable ; son numéro de parc reste réservé.
      </p>
    </ActionForm>
  );
}

function History({ vehicle: v, timeZone }: { vehicle: Vehicle; timeZone: string }) {
  const me = useMe();
  const statuses = useQuery({
    queryKey: ["vehicle-history", v.vehicle_id, "status"],
    queryFn: () => read("/vehicles/{vehicle_id}/status-history", { path: { vehicle_id: v.vehicle_id } }),
  });
  const canAssignments = can(me.grants, "assignment.vehicle_assignment.read", v.site_id);
  const assignments = useQuery({
    queryKey: ["vehicle-history", v.vehicle_id, "assignments"],
    enabled: canAssignments,
    queryFn: () =>
      read("/vehicles/{vehicle_id}/assignments", { path: { vehicle_id: v.vehicle_id }, query: { page_size: 20 } }),
  });
  return (
    <>
      <h2>Historique des statuts</h2>
      <DataState loading={statuses.isLoading} error={statuses.error} empty={(statuses.data ?? []).length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Statut</th>
              <th scope="col">Motif</th>
            </tr>
          </thead>
          <tbody>
            {(statuses.data ?? []).map((h) => (
              <tr key={`${h.changed_at}-${h.to_status}`}>
                <td>{formatDateTime(h.changed_at, timeZone)}</td>
                <td>
                  {h.from_status ? `${label(VEHICLE_STATUS, h.from_status)} → ` : ""}
                  {label(VEHICLE_STATUS, h.to_status)}
                </td>
                <td>{h.reason_code ? label(VEHICLE_REASONS, h.reason_code) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      {canAssignments && (
        <>
          <h2>Dernières affectations</h2>
          <DataState
            loading={assignments.isLoading}
            error={assignments.error}
            empty={(assignments.data?.items ?? []).length === 0}
            emptyText="Aucune affectation."
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">Conducteur</th>
                  <th scope="col">Début</th>
                  <th scope="col">Fin</th>
                  <th scope="col">Statut</th>
                </tr>
              </thead>
              <tbody>
                {(assignments.data?.items ?? []).map((a) => (
                  <tr key={a.vehicle_assignment_id}>
                    <td>{a.driver_display_name}</td>
                    <td>{formatDateTime(a.valid_from, timeZone)}</td>
                    <td>{formatDateTime(a.valid_to, timeZone)}</td>
                    <td>{label(ASSIGNMENT_STATUS, a.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataState>
        </>
      )}
    </>
  );
}
