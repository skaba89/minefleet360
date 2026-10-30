import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { read, type Schemas } from "../api/client";
import { Badge, DataState } from "../components/common";
import { Icon, type IconName } from "../components/Icon";

type FuelDashboardData = Schemas["FuelDashboardOut"];
type Trend = Schemas["FuelDashboardDailyOut"];

const PERIODS = { 7: "7 derniers jours", 30: "30 derniers jours", 90: "90 derniers jours" } as const;

function liters(value: string): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(Number(value))} L`;
}

function signedLiters(value: string): string {
  const amount = Number(value);
  return `${amount > 0 ? "+" : ""}${liters(value)}`;
}

function resolution(value: string | null): string {
  if (value === null) return "—";
  const hours = Number(value);
  if (hours < 24) return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(hours)} h`;
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(hours / 24)} j`;
}

function queryRange(days: number): { from: string; to: string } {
  const end = new Date();
  const start = new Date(end.getTime() - days * 24 * 60 * 60 * 1000);
  return { from: start.toISOString(), to: end.toISOString() };
}

function TrendChart({ rows }: { rows: Trend[] }) {
  const width = Math.max(620, rows.length * 18);
  const height = 220;
  const left = 42;
  const right = 16;
  const top = 20;
  const bottom = 32;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maximum = Math.max(1, ...rows.flatMap((row) => [Number(row.distributed_liters), Number(row.received_liters)]));
  const x = (index: number) => left + (rows.length === 1 ? plotWidth / 2 : index * plotWidth / (rows.length - 1));
  const y = (value: string) => top + plotHeight - Number(value) / maximum * plotHeight;
  const points = (field: "distributed_liters" | "received_liters") => rows.map((row, index) => `${x(index)},${y(row[field])}`).join(" ");
  const labelIndexes = new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1]);
  return <div className="fuel-chart-scroll">
    <svg viewBox={`0 0 ${width} ${height}`} className="fuel-trend-chart" role="img" aria-label="Tendance quotidienne des volumes distribués et réceptionnés">
      <title>Tendance quotidienne des volumes distribués et réceptionnés</title>
      {[0, .25, .5, .75, 1].map((ratio) => <g key={ratio}>
        <line x1={left} x2={width - right} y1={top + plotHeight * ratio} y2={top + plotHeight * ratio} className="fuel-grid-line" />
        <text x={left - 7} y={top + plotHeight * ratio + 4} textAnchor="end">{new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 }).format(maximum * (1 - ratio))}</text>
      </g>)}
      {rows.length > 1 && <>
        <polyline points={points("received_liters")} className="fuel-line fuel-line-received" />
        <polyline points={points("distributed_liters")} className="fuel-line fuel-line-distributed" />
      </>}
      {rows.map((row, index) => <g key={row.day}>
        <circle cx={x(index)} cy={y(row.received_liters)} r="3" className="fuel-point fuel-point-received"><title>{row.day} : {liters(row.received_liters)} réceptionnés</title></circle>
        <circle cx={x(index)} cy={y(row.distributed_liters)} r="3" className="fuel-point fuel-point-distributed"><title>{row.day} : {liters(row.distributed_liters)} distribués</title></circle>
        {labelIndexes.has(index) && <text x={x(index)} y={height - 8} textAnchor="middle">{new Date(`${row.day}T00:00:00Z`).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", timeZone: "UTC" })}</text>}
      </g>)}
    </svg>
  </div>;
}

function SiteChart({ rows }: { rows: FuelDashboardData["site_consumption"] }) {
  const maximum = Math.max(1, ...rows.map((row) => Number(row.liters)));
  return <svg viewBox={`0 0 520 ${rows.length * 46 + 15}`} className="site-chart" role="img" aria-label="Consommation de carburant par site">
    <title>Consommation de carburant par site</title>
    {rows.map((row, index) => <g key={row.site_id}>
      <text x="0" y={index * 46 + 25}>{row.site_code}</text>
      <rect x="85" y={index * 46 + 8} width="330" height="24" rx="4" className="fuel-site-track" />
      <rect x="85" y={index * 46 + 8} width={Number(row.liters) / maximum * 330} height="24" rx="4" className="fuel-site-bar" />
      <text x="430" y={index * 46 + 25}>{liters(row.liters)}</text>
      <title>{row.site_name} : {liters(row.liters)}</title>
    </g>)}
  </svg>;
}

export function FuelDashboard({ siteId, enabled }: { siteId: string | null; enabled: boolean }) {
  const [periodDays, setPeriodDays] = useState<keyof typeof PERIODS>(30);
  const dashboard = useQuery({
    queryKey: ["fuel-dashboard", siteId, periodDays],
    enabled,
    queryFn: () => {
      const range = queryRange(periodDays);
      return read("/fuel/dashboard", { query: { site_id: siteId, from: range.from, to: range.to } });
    },
    refetchInterval: 60_000,
  });
  if (!enabled) return null;
  const data = dashboard.data;
  const cards: { label: string; value: string; detail: string; icon: IconName; tone: string }[] = [
    { label: "Volumes distribués", value: data ? liters(data.distributed_liters) : "—", detail: PERIODS[periodDays], icon: "fuel", tone: "blue" },
    { label: "Volumes réceptionnés", value: data ? liters(data.received_liters) : "—", detail: "Entrées validées en cuve", icon: "truck", tone: "green" },
    { label: "Anomalies actives", value: data ? data.open_anomaly_cases.toLocaleString("fr-FR") : "—", detail: data ? `${data.closed_anomaly_cases} clôturée(s) sur la période` : "Dossiers à traiter", icon: "shield", tone: "amber" },
    { label: "Alertes de stock", value: data ? data.active_stock_alerts.toLocaleString("fr-FR") : "—", detail: data ? `${data.unacknowledged_stock_alerts} non prise(s) en compte` : "Alertes actives", icon: "bell", tone: "red" },
  ];
  return <section className="fuel-dashboard" aria-labelledby="fuel-dashboard-title">
    <div className="page-head">
      <div><h2 id="fuel-dashboard-title">Indicateurs carburant</h2><p className="muted">Volumes, écarts et points de vigilance de votre périmètre</p></div>
      <div className="fuel-dashboard-controls">
        <label>Période<select aria-label="Période du tableau de bord" value={periodDays} onChange={(event) => setPeriodDays(Number(event.target.value) as keyof typeof PERIODS)}>{Object.entries(PERIODS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button type="button" onClick={() => void dashboard.refetch()} disabled={dashboard.isFetching}>{dashboard.isFetching ? "Actualisation…" : "Actualiser"}</button>
      </div>
    </div>
    <div className="dashboard-metrics">{cards.map((card) => <div className="metric-card" key={card.label} aria-label={`${card.label} : ${card.value}`}>
      <span className={`metric-icon ${card.tone}`}><Icon name={card.icon} /></span><div><span>{card.label}</span><strong>{card.value}</strong><small>{card.detail}</small></div>
    </div>)}</div>
    <DataState loading={dashboard.isLoading} error={dashboard.error} empty={false}>
      {data && <>
        <div className="dashboard-panels">
          <div className="card"><div className="page-head"><div><h2>Tendance des volumes</h2><p className="muted small">Litres par jour · heure de Guinée (UTC)</p></div><div className="fuel-chart-legend"><span className="received">Réceptionnés</span><span className="distributed">Distribués</span></div></div>
            <TrendChart rows={data.daily_trend} />
          </div>
          <div className="card"><h2>Consommation par site</h2><p className="muted small">Sorties approuvées sur la période</p>
            {data.site_consumption.length === 0 ? <p className="muted">Aucune consommation enregistrée.</p> : <SiteChart rows={data.site_consumption} />}
          </div>
        </div>
        <div className="dashboard-panels fuel-dashboard-details">
          <div className="card"><h2>Véhicules les plus consommateurs</h2><p className="muted small">Top 10 selon les ravitaillements approuvés</p>
            {data.vehicle_consumption.length === 0 ? <p className="muted">Aucun ravitaillement approuvé sur la période.</p> : <table><thead><tr><th>Véhicule</th><th>Volume</th></tr></thead><tbody>{data.vehicle_consumption.map((row) => <tr key={row.vehicle_id}><td>{row.vehicle_fleet_number}</td><td><strong>{liters(row.liters)}</strong></td></tr>)}</tbody></table>}
          </div>
          <div className="card"><h2>Points de vigilance</h2><p className="muted small">Indicateurs de contrôle, sans conclusion automatique de fraude</p>
            <ul className="fuel-alert-list">
              <li><span>Délai moyen de résolution</span><strong>{resolution(data.average_resolution_hours)}</strong></li>
              <li><span>Écart des anomalies qualifiées</span><strong>{liters(data.qualified_anomaly_variance_liters)}</strong></li>
              <li><span>Écart net des inventaires</span><strong>{signedLiters(data.stocktake_variance_liters)}</strong></li>
              <li><span>Alertes non prises en compte</span><Badge tone={data.unacknowledged_stock_alerts > 0 ? "bad" : "ok"}>{data.unacknowledged_stock_alerts}</Badge></li>
            </ul>
          </div>
        </div>
      </>}
    </DataState>
  </section>;
}
