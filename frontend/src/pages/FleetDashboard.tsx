import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { get, type Schemas } from "../api/client";
import { DataState } from "../components/common";
import { Icon, type IconName } from "../components/Icon";
import { gpsSignalState, type GpsSignalPoint } from "../lib/gpsSignal";
import { label, VEHICLE_STATUS } from "../lib/labels";
import { useSites } from "../site/SiteContext";

interface VehiclePage { items: Schemas["VehicleOut"][]; total: number }
const states = ["AVAILABLE", "IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"];
const colors = ["#18b878", "#ffad26", "#6685ad", "#ef5665"];

export function FleetDashboard() {
  const { siteId, sites } = useSites();
  const counts = useQueries({ queries: states.map((status) => ({ queryKey: ["dashboard-status", siteId, status], queryFn: () => get<VehiclePage>("/vehicles", { site_id: siteId, status, page_size: 1 }), refetchInterval: 30_000 })) });
  const fleet = useQuery({ queryKey: ["dashboard-fleet", siteId], queryFn: () => get<VehiclePage>("/vehicles", { site_id: siteId, page_size: 5 }), refetchInterval: 30_000 });
  const gps = useQuery({ queryKey: ["gps-latest", siteId], queryFn: () => get<GpsSignalPoint[]>("/vehicles/gps/latest", { site_id: siteId }), refetchInterval: 15_000 });
  const siteRows = (siteId ? sites.filter((s) => s.site_id === siteId) : sites).slice(0, 6);
  const siteCounts = useQueries({ queries: siteRows.map((s) => ({ queryKey: ["dashboard-site", s.site_id], queryFn: () => get<VehiclePage>("/vehicles", { site_id: s.site_id, page_size: 1 }), refetchInterval: 30_000 })) });
  const total = fleet.data?.total ?? 0;
  const ready = counts.every((q) => q.isSuccess);
  const active = gps.data?.filter((p) => gpsSignalState(p, Date.now()) !== "offline").length;
  const values = counts.map((q) => q.data?.total ?? 0);
  const cards: { label: string; value: number | undefined; icon: IconName; tone: string; detail: string; to: string }[] = [
    { label: "Véhicules disponibles", value: counts[0]?.data?.total, icon: "truck", tone: "green", detail: fleet.data ? `Sur ${total} véhicules du parc` : "Parc de votre périmètre", to: "/vehicules" },
    { label: "Signaux GPS récents", value: gps.isSuccess ? active : undefined, icon: "gps", tone: "blue", detail: "Relevés et réception de moins de 2 min", to: "/flotte-gps" },
    { label: "À l'atelier", value: counts[1]?.data?.total, icon: "tool", tone: "amber", detail: "Véhicules en maintenance", to: "/atelier" },
    { label: "Indisponibles", value: ready ? (values[2] ?? 0) + (values[3] ?? 0) : undefined, icon: "shield", tone: "red", detail: "Immobilisés ou hors service", to: "/vehicules" },
  ];
  let cumulative = 0;
  return <section>
    <div className="page-head"><div><h1>Tableau de bord</h1><p className="muted">Vue d'ensemble de votre exploitation</p></div><span className="dashboard-live"><span className="connection-dot" />Données actualisées automatiquement</span></div>
    <div className="dashboard-metrics">{cards.map((c) => <Link className="metric-card" key={c.label} to={c.to}><span className={`metric-icon ${c.tone}`}><Icon name={c.icon} /></span><div><span>{c.label}</span><strong>{c.value === undefined ? "—" : c.value.toLocaleString("fr-FR")}</strong><small>{c.detail}</small></div></Link>)}</div>
    {[...counts, fleet, gps].some((q) => q.isError) && <p role="alert" className="error">Certains indicateurs ne sont pas disponibles. Les tirets signalent les données non reçues.</p>}
    <div className="dashboard-panels">
      <div className="card"><h2>Parc par site</h2><p className="muted small">Véhicules non réformés · {siteRows.length} site(s) affiché(s)</p>{siteRows.length === 0 ? <p className="muted">Aucun site disponible.</p> : <svg viewBox={`0 0 500 ${siteRows.length * 43 + 15}`} className="site-chart" role="img" aria-label="Nombre de véhicules par site">{siteRows.map((site, i) => {
        const value = siteCounts[i]?.data?.total;
        const max = Math.max(1, ...siteCounts.map((q) => q.data?.total ?? 0));
        return <g key={site.site_id}><text x="0" y={i * 43 + 22}>{site.code}</text><rect x="90" y={i * 43 + 6} width="350" height="22" rx="4" fill="#edf3fa" /><rect x="90" y={i * 43 + 6} width={(value ?? 0) / max * 350} height="22" rx="4" fill="#1784ef" /><text x="455" y={i * 43 + 22}>{value ?? "—"}</text><title>{site.name} : {value ?? "indisponible"}</title></g>;
      })}</svg>}{siteCounts.some((q) => q.isError) && <p className="warn-text small">Le comptage de certains sites est indisponible.</p>}</div>
      <div className="card"><h2>Répartition des états</h2><p className="muted small">Parc total : {fleet.data ? total : "—"} véhicule(s)</p><div className="status-distribution"><svg viewBox="0 0 180 180" className="donut-chart" role="img" aria-label="Répartition des statuts des véhicules"><circle cx="90" cy="90" r="65" fill="none" stroke="#edf3fa" strokeWidth="24" />{ready && total > 0 && values.map((v, i) => { const start = cumulative; cumulative += v / total * 100; return <circle key={states[i]} cx="90" cy="90" r="65" fill="none" stroke={colors[i]} strokeWidth="24" pathLength="100" strokeDasharray={`${v / total * 100} ${100 - v / total * 100}`} strokeDashoffset={-start} transform="rotate(-90 90 90)" />; })}<text x="90" y="88" textAnchor="middle" className="donut-total">{fleet.data ? total : "—"}</text><text x="90" y="107" textAnchor="middle" className="donut-caption">véhicules</text></svg><ul className="status-legend">{states.map((s, i) => <li key={s}><span className={`legend-dot legend-dot-${i}`} />{label(VEHICLE_STATUS, s)}<strong>{counts[i]?.data?.total ?? "—"}</strong></li>)}</ul></div></div>
    </div>
    <div className="card"><div className="page-head"><div><h2>Votre parc de véhicules</h2><p className="muted small">Premiers véhicules par numéro de parc</p></div><Link to="/vehicules">Voir tous les véhicules →</Link></div><DataState loading={fleet.isLoading} error={fleet.error} empty={fleet.data?.items.length === 0}><table><thead><tr><th>N° de parc</th><th>Immatriculation</th><th>Marque / modèle</th><th>État</th><th>Accès</th></tr></thead><tbody>{fleet.data?.items.map((v) => <tr key={v.vehicle_id}><td><Link to={`/vehicules/${v.vehicle_id}`}>{v.fleet_number}</Link></td><td>{v.registration_number ?? "—"}</td><td>{[v.make, v.model].filter(Boolean).join(" ") || "—"}</td><td><span className={`badge badge-${v.status === "AVAILABLE" ? "ok" : v.status === "IN_MAINTENANCE" ? "warn" : "bad"}`}>{label(VEHICLE_STATUS, v.status)}</span></td><td><Link to={`/vehicules/${v.vehicle_id}`}>Ouvrir</Link></td></tr>)}</tbody></table></DataState></div>
  </section>;
}
