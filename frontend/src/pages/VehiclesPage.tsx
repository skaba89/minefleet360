import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, Pager } from "../components/common";
import { ActionForm, intOrNull, Options, orNull } from "../components/forms";
import { FUEL, label, OWNERSHIP, VEHICLE_STATUS } from "../lib/labels";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

type VehicleCreate = Schemas["VehicleCreate"];
export type VehicleStatusCode = "AVAILABLE" | "IN_MAINTENANCE" | "IMMOBILIZED" | "OUT_OF_SERVICE" | "RETIRED";

const PAGE_SIZE = 50;
export const VEHICLE_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  AVAILABLE: "ok",
  IN_MAINTENANCE: "warn",
  IMMOBILIZED: "bad",
  OUT_OF_SERVICE: "bad",
  RETIRED: "neutral",
};

export function useCategories() {
  return useQuery({ queryKey: ["vehicle-categories"], queryFn: () => read("/vehicle-categories") });
}

export function VehiclesPage() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const vehicles = useQuery({
    queryKey: ["vehicles", siteId, status, page],
    queryFn: () =>
      read("/vehicles", {
        query: {
          site_id: siteId,
          status: (status || null) as VehicleStatusCode | null,
          include_retired: status === "RETIRED",
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const categories = useCategories();
  const categoryLabel = new Map((categories.data ?? []).map((c) => [c.vehicle_category_id, c.label_fr]));
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = vehicles.data?.items ?? [];

  return (
    <section>
      <div className="page-head">
        <h1>Véhicules et engins</h1>
        {can(me.grants, "fleet.vehicle.create") && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouveau véhicule
          </button>
        )}
      </div>
      {creating && <CreateVehicle onClose={() => setCreating(false)} />}
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
            <option value="">Tous (hors réformés)</option>
            <Options map={VEHICLE_STATUS} />
          </select>
        </label>
      </div>
      <DataState loading={vehicles.isLoading} error={vehicles.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">N° de parc</th>
              <th scope="col">Catégorie</th>
              <th scope="col">Immatriculation</th>
              <th scope="col">Site</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.vehicle_id}>
                <td>
                  <Link to={`/vehicules/${v.vehicle_id}`}>{v.fleet_number}</Link>
                </td>
                <td>{categoryLabel.get(v.vehicle_category_id) ?? "—"}</td>
                <td>{v.registration_number ?? "—"}</td>
                <td>{siteCode.get(v.site_id) ?? "—"}</td>
                <td>
                  <Badge tone={VEHICLE_TONE[v.status] ?? "neutral"}>{label(VEHICLE_STATUS, v.status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={vehicles.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function CreateVehicle({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { sites, siteId } = useSites();
  const categories = useCategories();
  const allowedSites = sites.filter((s) => s.status === "ACTIVE" && can(me.grants, "fleet.vehicle.create", s.site_id));
  const [form, setForm] = useState({
    site_id: siteId ?? allowedSites[0]?.site_id ?? "",
    vehicle_category_id: "",
    fleet_number: "",
    registration_number: "",
    serial_number: "",
    make: "",
    model: "",
    model_year: "",
    ownership_type: "OWNED",
    fuel_type: "",
    rated_payload_kg: "",
    commissioned_on: "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  return (
    <ActionForm
      title="Nouveau véhicule"
      submitLabel="Créer le véhicule"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/vehicles", {
          body: {
            site_id: form.site_id,
            vehicle_category_id: form.vehicle_category_id,
            fleet_number: form.fleet_number.trim(),
            registration_number: orNull(form.registration_number),
            serial_number: orNull(form.serial_number),
            make: orNull(form.make),
            model: orNull(form.model),
            model_year: intOrNull(form.model_year),
            ownership_type: form.ownership_type as VehicleCreate["ownership_type"],
            fuel_type: orNull(form.fuel_type) as VehicleCreate["fuel_type"],
            rated_payload_kg: intOrNull(form.rated_payload_kg),
            commissioned_on: orNull(form.commissioned_on),
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["vehicles"] });
        navigate(`/vehicules/${data.vehicle_id}`);
      }}
    >
      <label>
        Site
        <select required value={form.site_id} onChange={set("site_id")}>
          <option value="">— Choisir —</option>
          {allowedSites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Catégorie
        <select required value={form.vehicle_category_id} onChange={set("vehicle_category_id")}>
          <option value="">— Choisir —</option>
          {(categories.data ?? [])
            .filter((c) => c.is_active)
            .map((c) => (
              <option key={c.vehicle_category_id} value={c.vehicle_category_id}>
                {c.label_fr}
              </option>
            ))}
        </select>
      </label>
      <label>
        N° de parc (unique, définitif)
        <input required pattern="\S{1,30}" maxLength={30} value={form.fleet_number} onChange={set("fleet_number")} />
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
        Charge utile nominale (kg, constructeur)
        <input type="number" min={1} value={form.rated_payload_kg} onChange={set("rated_payload_kg")} />
      </label>
      <label>
        Mise en service
        <input type="date" value={form.commissioned_on} onChange={set("commissioned_on")} />
      </label>
    </ActionForm>
  );
}
