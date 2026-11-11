import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { read } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, Badge, DataState } from "../components/common";
import { Fact } from "../components/forms";
import { label, VEHICLE_STATUS } from "../lib/labels";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

const PERIODS: Record<string, string> = { "30": "30 jours", "90": "90 jours", "180": "180 jours", "365": "365 jours" };
const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

function hours(value: string | null | undefined): string {
  return value == null ? "—" : `${number.format(Number(value))} h`;
}

function cost(value: string | null | undefined, complete: boolean, currency: string | null | undefined): string {
  if (value == null) return "—";
  const amount = `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(value))}${currency ? ` ${currency}` : ""}`;
  return complete ? amount : `≥ ${amount}`;
}

function tone(percent: string): "ok" | "warn" | "bad" {
  const value = Number(percent);
  return value >= 90 ? "ok" : value >= 75 ? "warn" : "bad";
}

/** Fiabilité du parc : disponibilité, MTBF, MTTR, main-d'œuvre et coût pièces par engin (source : atelier). */
export function ReliabilityPage() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const [days, setDays] = useState("90");
  const allowed = can(me.grants, "maintenance.reliability.read", siteId);
  const report = useQuery({
    queryKey: ["maintenance-reliability", siteId, days],
    enabled: allowed,
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - Number(days) * 86_400_000);
      return read("/maintenance/reliability", { query: { site_id: siteId, from: from.toISOString(), to: to.toISOString() } });
    },
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const r = report.data;
  return (
    <section>
      <Link className="back" to="/atelier">
        ← Atelier
      </Link>
      <div className="page-head">
        <h1>Fiabilité du parc</h1>
      </div>
      {!allowed ? (
        <AccessDenied />
      ) : (
        <>
          <div className="filters">
            <label>
              Période
              <select value={days} onChange={(e) => setDays(e.target.value)}>
                {Object.entries(PERIODS).map(([code, text]) => (
                  <option key={code} value={code}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <DataState loading={report.isLoading} error={report.error} empty={!r || r.vehicles.length === 0} emptyText="Aucun engin dans ce périmètre.">
            {r && (
              <>
                <dl className="facts" aria-label="Synthèse du parc">
                  <Fact label="Engins">{r.totals.vehicles}</Fact>
                  <Fact label="Disponibilité">{r.totals.availability_percent == null ? null : `${number.format(Number(r.totals.availability_percent))} %`}</Fact>
                  <Fact label="Pannes">{r.totals.failures}</Fact>
                  <Fact label="MTBF moyen">{hours(r.totals.mtbf_hours)}</Fact>
                  <Fact label="Délai moyen de remise en service (MTTR)">{hours(r.totals.mttr_hours)}</Fact>
                  <Fact label="Immobilisation cumulée">{hours(r.totals.downtime_hours)}</Fact>
                  <Fact label="Main-d'œuvre (OT clôturés)">{hours(r.totals.labour_hours)}</Fact>
                  <Fact label="Pièces consommées (OT clôturés)">{cost(r.totals.parts_cost_known, r.totals.parts_cost_complete, r.currency)}</Fact>
                </dl>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Engin</th>
                      <th scope="col">Disponibilité</th>
                      <th scope="col">Pannes</th>
                      <th scope="col">MTBF</th>
                      <th scope="col">MTTR</th>
                      <th scope="col">Immobilisation</th>
                      <th scope="col">Main-d'œuvre</th>
                      <th scope="col">Pièces</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.vehicles.map((v) => (
                      <tr key={v.vehicle_id}>
                        <td>
                          <Link to={`/vehicules/${v.vehicle_id}`}>{v.fleet_number}</Link>
                          <div className="small muted">
                            {siteCode.get(v.site_id)} — {label(VEHICLE_STATUS, v.vehicle_status)}
                            {v.open_work_orders > 0 && ` — ${v.open_work_orders} OT ouvert${v.open_work_orders > 1 ? "s" : ""}`}
                          </div>
                        </td>
                        <td>
                          <Badge tone={tone(v.availability_percent)}>{number.format(Number(v.availability_percent))} %</Badge>
                        </td>
                        <td>{v.failures}</td>
                        <td>{hours(v.mtbf_hours)}</td>
                        <td>{hours(v.mttr_hours)}</td>
                        <td>{hours(v.downtime_hours)}</td>
                        <td>{hours(v.labour_hours)}</td>
                        <td>{cost(v.parts_cost_known, v.parts_cost_complete, r.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="muted small">
                  Indicateurs calculés à partir des ordres de travail : immobilisation = panne bloquante ou intervention en cours,
                  sans double comptage. « ≥ » signale des sorties de pièces non valorisées (coût réel supérieur). Un engin sans OT
                  apparaît disponible selon l'atelier, sans mesure terrain.
                </p>
              </>
            )}
          </DataState>
        </>
      )}
    </section>
  );
}
