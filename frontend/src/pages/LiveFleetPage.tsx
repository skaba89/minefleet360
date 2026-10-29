import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { get } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState } from "../components/common";
import { can } from "../lib/permissions";
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
}

type SignalState = "moving" | "stopped" | "offline";

function signalState(point: GpsPosition, now: number): SignalState {
  const timestamp = Date.parse(point.received_at);
  if (!Number.isFinite(timestamp) || now - timestamp > 120_000 || timestamp > now + 120_000) {
    return "offline";
  }
  return (point.speed_kmh ?? 0) > 2 ? "moving" : "stopped";
}

const STATUS_LABEL: Record<SignalState, string> = {
  moving: "En mouvement",
  stopped: "À l'arrêt",
  offline: "Signal ancien",
};

export function LiveFleetPage() {
  const me = useMe();
  const { siteId } = useSites();
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const permitted = can(me.grants, "fleet.vehicle.read", siteId);
  const gps = useQuery({
    queryKey: ["gps-latest", siteId],
    queryFn: () => get<GpsPosition[]>("/vehicles/gps/latest", siteId ? { site_id: siteId } : undefined),
    refetchInterval: 15_000,
    enabled: permitted,
  });
  const shown = useMemo(
    () => (gps.data ?? []).filter((item) => item.vehicle_id.toLowerCase().includes(search.toLowerCase())),
    [gps.data, search],
  );
  if (!permitted) return <p>Accès à la flotte non autorisé.</p>;
  const selected = shown.find((point) => point.vehicle_id === selectedId);

  const moving = shown.filter((item) => signalState(item, now) === "moving").length;
  const offline = shown.filter((item) => signalState(item, now) === "offline").length;
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
      </div>
      <div className="live-fleet-metrics" aria-label="État des signaux GPS">
        <div className="card"><span className="muted">Camions localisés</span><strong>{shown.length}</strong></div>
        <div className="card"><span className="muted">En mouvement</span><strong>{moving}</strong></div>
        <div className="card"><span className="muted">Signal ancien</span><strong>{offline}</strong></div>
      </div>
      <div className="card">
        <label htmlFor="gps-search">Rechercher un identifiant de camion</label>
        <input id="gps-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Identifiant véhicule" />
      </div>
      {selected ? <GpsLocationMap key={selected.vehicle_id} point={selected} /> : null}
      <DataState loading={gps.isLoading} error={gps.error} empty={shown.length === 0} emptyText="Aucune position GPS disponible pour ce périmètre.">
        <div className="live-fleet-table">
          <table>
            <thead><tr><th>Camion</th><th>État du signal</th><th>Vitesse</th><th>Coordonnées</th><th>Dernière réception</th><th>Carte</th></tr></thead>
            <tbody>
              {shown.map((point) => {
                const state = signalState(point, now);
                return (
                  <tr key={point.vehicle_id}>
                    <td><Link to={`/vehicules/${point.vehicle_id}`}>{point.vehicle_id.slice(0, 8)}</Link></td>
                    <td><span className={`gps-status gps-status--${state}`}>{STATUS_LABEL[state]}</span></td>
                    <td>{point.speed_kmh == null ? "—" : `${point.speed_kmh.toFixed(1)} km/h`}</td>
                    <td>{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</td>
                    <td>{new Date(point.received_at).toLocaleString("fr-FR")}</td>
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
