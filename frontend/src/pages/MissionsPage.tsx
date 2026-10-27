import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, Pager } from "../components/common";
import { ActionForm, intOrNull, Options } from "../components/forms";
import { label, LOCATION_KINDS, MISSION_STATUS, MISSION_TONE } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type MissionStatusCode = Schemas["MissionOut"]["status"];
const PAGE_SIZE = 50;

export function MissionsPage() {
  const me = useMe();
  const { siteId, sites, timezoneOf } = useSites();
  const [status, setStatus] = useState("");
  const [openOnly, setOpenOnly] = useState(true);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const missions = useQuery({
    queryKey: ["missions", siteId, status, openOnly, page],
    queryFn: () =>
      read("/missions", {
        query: {
          site_id: siteId,
          status: (status || null) as MissionStatusCode | null,
          open_only: openOnly,
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = missions.data?.items ?? [];

  return (
    <section>
      <div className="page-head">
        <h1>Missions de transport</h1>
        {can(me.grants, "dispatch.mission.create", siteId) && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouvelle mission
          </button>
        )}
      </div>
      {creating && <CreateMission onClose={() => setCreating(false)} />}
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
            <Options map={MISSION_STATUS} empty="Tous" />
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
          En cours seulement
        </label>
      </div>
      <DataState loading={missions.isLoading} error={missions.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Début prévu</th>
              <th scope="col">Véhicule</th>
              <th scope="col">Conducteur</th>
              <th scope="col">Trajet</th>
              <th scope="col">Matière</th>
              <th scope="col">Rotations</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.mission_id}>
                <td>
                  <Link to={`/missions/${m.mission_id}`}>{formatDateTime(m.planned_start, timezoneOf(m.site_id))}</Link>
                  <div className="small muted">{siteCode.get(m.site_id)}</div>
                </td>
                <td>{m.vehicle_fleet_number}</td>
                <td>{m.driver_display_name}</td>
                <td>
                  {m.origin_name} → {m.destination_name}
                </td>
                <td>{m.material_name}</td>
                <td>
                  {m.rotations_completed}
                  {m.planned_rotations ? ` / ${m.planned_rotations}` : ""}
                </td>
                <td>
                  <Badge tone={MISSION_TONE[m.status] ?? "neutral"}>{label(MISSION_STATUS, m.status)}</Badge>
                  {m.overdue && <div className="warn-text small">Échéance dépassée</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={missions.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function CreateMission({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { siteId, timezoneOf } = useSites();
  // Affectations en cours ou planifiées : elles portent le véhicule et le conducteur éligibles (RM-080).
  const assignments = useQuery({
    queryKey: ["assignments", "for-mission", siteId],
    queryFn: async () => {
      const [active, planned] = await Promise.all(
        (["ACTIVE", "PLANNED"] as const).map((status) =>
          read("/vehicle-assignments", { query: { site_id: siteId, status, page_size: 200 } }),
        ),
      );
      return [...(active?.items ?? []), ...(planned?.items ?? [])];
    },
  });
  const [form, setForm] = useState({
    vehicle_assignment_id: "",
    origin_location_id: "",
    destination_location_id: "",
    material_id: "",
    planned_start: utcToZonedInput(new Date(), timezoneOf(siteId)),
    due_at: "",
    planned_rotations: "",
  });
  const assignment = useMemo(
    () => assignments.data?.find((a) => a.vehicle_assignment_id === form.vehicle_assignment_id),
    [assignments.data, form.vehicle_assignment_id],
  );
  const timeZone = timezoneOf(assignment?.site_id ?? siteId);
  const locations = useQuery({
    queryKey: ["site-locations", assignment?.site_id],
    enabled: Boolean(assignment),
    queryFn: () => read("/site-locations", { query: { site_id: assignment?.site_id } }),
  });
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => read("/materials") });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const places = locations.data ?? [];

  return (
    <ActionForm
      title="Nouvelle mission"
      submitLabel="Créer la mission"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/missions", {
          body: {
            vehicle_assignment_id: form.vehicle_assignment_id,
            origin_location_id: form.origin_location_id,
            destination_location_id: form.destination_location_id,
            material_id: form.material_id,
            planned_start: zonedInputToUtc(form.planned_start, timeZone).toISOString(),
            due_at: form.due_at ? zonedInputToUtc(form.due_at, timeZone).toISOString() : null,
            planned_rotations: intOrNull(form.planned_rotations),
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["missions"] });
        navigate(`/missions/${data.mission_id}`);
      }}
    >
      <label>
        Véhicule et conducteur (affectation)
        <select required value={form.vehicle_assignment_id} onChange={set("vehicle_assignment_id")}>
          <option value="">— Choisir —</option>
          {(assignments.data ?? []).map((a) => (
            <option key={a.vehicle_assignment_id} value={a.vehicle_assignment_id}>
              {a.vehicle_fleet_number} — {a.driver_display_name}
              {a.status === "PLANNED" ? " (planifiée)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Origine
        <select required disabled={!assignment} value={form.origin_location_id} onChange={set("origin_location_id")}>
          <option value="">— Choisir —</option>
          {places.map((p) => (
            <option key={p.site_location_id} value={p.site_location_id}>
              {p.name} ({label(LOCATION_KINDS, p.kind)})
            </option>
          ))}
        </select>
      </label>
      <label>
        Destination
        <select
          required
          disabled={!assignment}
          value={form.destination_location_id}
          onChange={set("destination_location_id")}
        >
          <option value="">— Choisir —</option>
          {places
            .filter((p) => p.site_location_id !== form.origin_location_id)
            .map((p) => (
              <option key={p.site_location_id} value={p.site_location_id}>
                {p.name} ({label(LOCATION_KINDS, p.kind)})
              </option>
            ))}
        </select>
      </label>
      <label>
        Matière
        <select required value={form.material_id} onChange={set("material_id")}>
          <option value="">— Choisir —</option>
          {(materials.data ?? []).map((m) => (
            <option key={m.material_id} value={m.material_id}>
              {m.name}
              {m.is_waste ? " (stérile)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label>
        Début prévu (heure du site)
        <input type="datetime-local" required value={form.planned_start} onChange={set("planned_start")} />
      </label>
      <label>
        Échéance (facultative)
        <input type="datetime-local" value={form.due_at} onChange={set("due_at")} />
      </label>
      <label>
        Rotations prévues (facultatif)
        <input type="number" min={1} max={500} value={form.planned_rotations} onChange={set("planned_rotations")} />
      </label>
      {assignment && places.length < 2 && (
        <p className="warn-text small">
          Ce site a moins de deux lieux actifs : déclarez-les dans Administration › Lieux et matières.
        </p>
      )}
    </ActionForm>
  );
}

