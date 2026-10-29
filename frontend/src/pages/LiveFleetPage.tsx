import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState } from "../components/common";
import { can } from "../lib/permissions";
import { GPS_SIGNAL_LABEL, gpsSignalState } from "../lib/gpsSignal";
import { formatDateTime } from "../lib/time";
import { FleetPositionsOverview } from "./FleetPositionsOverview";
import { GpsLocationMap } from "./GpsLocationMap";
import { useSites } from "../site/SiteContext";

interface GpsPosition {
  vehicle_id: string;
  site_id: string;
  latitude: number;
  longitude: number;
  speed_kmh: number | null;
  accuracy_m: number | null;
  recorded_at: string;
  received_at: string;
  source?: "PHONE" | "TRACKER";
  source_active?: boolean;
}

export function LiveFleetPage() {
  const me = useMe();
  const { siteId, timezoneOf } = useSites();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(interval);
  }, []);
  const permitted = can(me.grants, "fleet.vehicle.read", siteId);
  const gps = useQuery({
    queryKey: ["gps-latest", siteId],
    queryFn: () => get<GpsPosition[]>("/vehicles/gps/latest", siteId ? { site_id: siteId } : undefined),
    refetchInterval: 15_000,
    enabled: permitted,
  });
  const vehicles = useQuery({ queryKey: ["gps-vehicle-labels", siteId], queryFn: () => get<{ items: Schemas["VehicleOut"][] }>("/vehicles", { site_id: siteId, page_size: 200 }), enabled: permitted });
  const byId = useMemo(() => new Map((vehicles.data?.items ?? []).map((v) => [v.vehicle_id, v])), [vehicles.data]);
  const vehicleLabel = (id: string) => byId.get(id)?.registration_number || byId.get(id)?.fleet_number || id.slice(0, 8);
  const shown = useMemo(
    () => (gps.data ?? []).filter((item) => [item.vehicle_id, byId.get(item.vehicle_id)?.fleet_number, byId.get(item.vehicle_id)?.registration_number].some((value) => value?.toLowerCase().includes(search.toLowerCase()))),
    [gps.data, search, byId],
  );
  if (!permitted) return <p>Accès à la flotte non autorisé.</p>;
  const selected = shown.find((point) => point.vehicle_id === selectedId);

  const moving = shown.filter((item) => gpsSignalState(item, now) === "moving").length;
  const offline = shown.filter((item) => gpsSignalState(item, now) === "offline").length;
  return (
    <section className="live-fleet">
      <div className="page-head">
        <div>
          <p className="live-fleet-eyebrow">CENTRE DE SUPERVISION</p>
          <h1>Flotte GPS</h1>
          <p className="muted">Dernières positions connues · actualisation toutes les 15 secondes</p>
        </div>
        <button type="button" onClick={() => { setNow(Date.now()); void gps.refetch(); }}>
          Actualiser
        </button>
        {can(me.grants, "fleet.gps.share", siteId) && <Link className="button-link" to="/mon-suivi">Partager mon téléphone</Link>}
      </div>
      <div className="live-fleet-metrics" aria-label="État des signaux GPS">
        <div className="card"><span className="muted">Camions localisés</span><strong>{shown.length}</strong></div>
        <div className="card"><span className="muted">En mouvement</span><strong>{moving}</strong></div>
        <div className="card"><span className="muted">Signal ancien</span><strong>{offline}</strong></div>
        <div className="card"><span className="muted">Téléphones localisés</span><strong>{shown.filter((p) => p.source === "PHONE").length}</strong></div>
      </div>
      <div className="gps-workspace">
        {selected ? <GpsLocationMap key={selected.vehicle_id} point={selected} now={now} timezone={timezoneOf(selected.site_id)} /> : <FleetPositionsOverview points={shown} selectedId={selectedId} onSelect={setSelectedId} now={now} />}
        <aside className="card" aria-label="Liste des véhicules GPS"><div className="page-head"><h2>Véhicules</h2>{selectedId && <button type="button" className="link" onClick={() => setSelectedId(null)}>Vue d'ensemble</button>}</div>
          <label htmlFor="gps-search">Rechercher un véhicule</label><input id="gps-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Immatriculation, n° de parc…" />
          <div className="gps-vehicle-list">{shown.map((p) => <button type="button" key={p.vehicle_id} aria-pressed={p.vehicle_id === selectedId} onClick={() => setSelectedId(p.vehicle_id)}><span className="connection-dot" /><span><strong>{vehicleLabel(p.vehicle_id)}</strong><small>{p.source === "PHONE" ? "Téléphone du compte" : "Traceur GPS"}{p.source_active === false ? " · partage arrêté" : ""}</small></span><span className={`gps-status gps-status--${gpsSignalState(p, now)}`}>{GPS_SIGNAL_LABEL[gpsSignalState(p, now)]}</span></button>)}</div>
        </aside>
      </div>
      {vehicles.error && <p className="muted small">Les noms du parc sont indisponibles ; les identifiants des véhicules restent affichés.</p>}
      <DataState loading={gps.isLoading} error={gps.error} empty={shown.length === 0} emptyText="Aucune position GPS disponible pour ce périmètre.">
        <div className="live-fleet-table">
          <table>
            <thead><tr><th>Véhicule</th><th>Source</th><th>État du signal</th><th>Vitesse</th><th>Coordonnées</th><th>Heure du relevé (site)</th><th>Réception (site)</th><th>Carte</th></tr></thead>
            <tbody>
              {shown.map((point) => {
                const state = gpsSignalState(point, now);
                return (
                  <tr key={point.vehicle_id}>
                    <td><Link to={`/vehicules/${point.vehicle_id}`}>{vehicleLabel(point.vehicle_id)}</Link></td>
                    <td>{point.source === "PHONE" ? "Téléphone" : "Traceur GPS"}{point.source_active === false && <small className="muted"> · arrêté</small>}</td>
                    <td><span className={`gps-status gps-status--${state}`}>{GPS_SIGNAL_LABEL[state]}</span></td>
                    <td>{state === "offline" || state === "unknown" ? "—" : `${point.speed_kmh!.toFixed(1)} km/h`}</td>
                    <td>{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</td>
                    <td>{Number.isFinite(Date.parse(point.recorded_at)) ? formatDateTime(point.recorded_at, timezoneOf(point.site_id)) : "—"}</td>
                    <td>{Number.isFinite(Date.parse(point.received_at)) ? formatDateTime(point.received_at, timezoneOf(point.site_id)) : "—"}</td>
                    <td><button type="button" onClick={() => setSelectedId(point.vehicle_id)}>Localiser</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </DataState>
      <p className="muted small">
        Une position ancienne ne signifie pas que le camion est actuellement à cet endroit.
        Les positions sont fournies par les équipements autorisés ; aucune simulation n'est affichée ici.
      </p>
    </section>
  );
}
