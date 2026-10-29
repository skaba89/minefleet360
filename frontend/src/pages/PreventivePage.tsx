import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState } from "../components/common";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";
import { VehiclePreventiveDues } from "./VehiclePreventiveDues";
import { VehiclePreventivePlans } from "./VehiclePreventivePlans";

export function PreventivePage() {
  const me = useMe();
  const { siteId } = useSites();
  const [vehicleId, setVehicleId] = useState("");
  const permitted = can(me.grants, "maintenance.preventive.read", siteId);
  const vehicles = useQuery({ queryKey: ["preventive-vehicle-choices", siteId], queryFn: () => get<{ items: Schemas["VehicleOut"][] }>("/vehicles", { site_id: siteId, page_size: 200 }), enabled: permitted && can(me.grants, "fleet.vehicle.read", siteId) });
  const selected = vehicles.data?.items.find((v) => v.vehicle_id === vehicleId);
  if (!permitted) return <p>Accès à la maintenance préventive non autorisé.</p>;
  return <section><div className="page-head"><div><h1>Maintenance préventive</h1><p className="muted">Suivi des plans et échéances d'entretien par véhicule</p></div></div><div className="card"><DataState loading={vehicles.isLoading} error={vehicles.error} empty={vehicles.data?.items.length === 0}><label>Véhicule<select value={selected?.vehicle_id ?? ""} onChange={(e) => setVehicleId(e.target.value)}><option value="">Choisir un véhicule</option>{vehicles.data?.items.map((v) => <option value={v.vehicle_id} key={v.vehicle_id}>{v.fleet_number}{v.registration_number ? ` · ${v.registration_number}` : ""}</option>)}</select></label></DataState></div>{selected ? <><VehiclePreventivePlans key={`plans-${selected.vehicle_id}`} vehicleId={selected.vehicle_id} siteId={selected.site_id} /><VehiclePreventiveDues key={`dues-${selected.vehicle_id}`} vehicleId={selected.vehicle_id} siteId={selected.site_id} /></> : <div className="card"><p className="muted">Sélectionnez un véhicule pour consulter ses échéances et gérer ses plans d'entretien.</p></div>}</section>;
}
