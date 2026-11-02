import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ActionForm } from "../components/forms";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

type VehicleCost = Schemas["VehicleCost"];
type Component = Schemas["Component"];
type Status = Component["status"];

const STATUS_LABEL: Record<Status, string> = {
  COMPLETE: "Complet",
  PARTIAL: "Partiel (minimum)",
  ESTIMATED: "Estimé",
  INSUFFICIENT: "Données insuffisantes",
};
const STATUS_TONE: Record<Status, "ok" | "warn" | "bad" | "neutral"> = {
  COMPLETE: "ok",
  ESTIMATED: "warn",
  PARTIAL: "warn",
  INSUFFICIENT: "bad",
};
const PERIODS: Record<string, string> = { "30": "30 jours", "90": "90 jours", "180": "180 jours", "365": "365 jours" };

function money(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "Données insuffisantes";
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(value))}${currency ? ` ${currency}` : ""}`;
}

function quantity(value: string, unit: string): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 }).format(Number(value))} ${unit}`;
}

function Cell({ c }: { c: Component }) {
  return (
    <>
      {c.status === "INSUFFICIENT" ? "—" : money(c.amount, c.currency)}
      {c.status !== "COMPLETE" && (
        <div>
          <Badge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
        </div>
      )}
    </>
  );
}

/** Coût complet par engin : carburant, pièces, main-d'œuvre valorisée, pneus ; coûts unitaires et classement. */
export function CostsPage() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const [days, setDays] = useState("30");
  const [selected, setSelected] = useState<VehicleCost | null>(null);
  const report = useQuery({
    queryKey: ["vehicle-costs", siteId, days],
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - Number(days) * 86_400_000);
      return read("/costs/vehicles", { query: { site_id: siteId, from: from.toISOString(), to: to.toISOString() } });
    },
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const rows = report.data?.vehicles ?? [];
  return (
    <section>
      <div className="page-head">
        <h1>Coût complet par engin</h1>
      </div>
      <p className="muted small">
        Coût complet = carburant + pièces + main-d'œuvre valorisée + pneus. « Estimé » : carburant au prix moyen pondéré des
        livraisons sur commande de la cuve, pneus amortis au kilomètre mesuré. « Partiel » : certains éléments ne sont pas
        valorisés (le montant est un minimum). Aucune conversion de devises n'est faite.
      </p>
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
      <DataState loading={report.isLoading} error={report.error} empty={rows.length === 0} emptyText="Aucun engin dans ce périmètre.">
        <table>
          <thead>
            <tr>
              <th scope="col">Engin</th>
              <th scope="col">Carburant</th>
              <th scope="col">Pièces</th>
              <th scope="col">Main-d'œuvre</th>
              <th scope="col">Pneus</th>
              <th scope="col">Total</th>
              <th scope="col">Coûts unitaires</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((v) => (
              <tr key={v.vehicle_id}>
                <td>
                  <button type="button" className="link" onClick={() => setSelected(v)}>
                    {v.fleet_number}
                  </button>
                  <div className="small muted">{siteCode.get(v.site_id)}</div>
                </td>
                <td>
                  <Cell c={v.fuel} />
                </td>
                <td>
                  <Cell c={v.parts} />
                </td>
                <td>
                  <Cell c={v.labour} />
                </td>
                <td>
                  <Cell c={v.tyres} />
                </td>
                <td>
                  <strong>{money(v.total, v.currency)}</strong>
                  <div>
                    <Badge tone={STATUS_TONE[v.total_status]}>{STATUS_LABEL[v.total_status]}</Badge>
                  </div>
                  {v.missing.length > 0 && <div className="small muted">Manque : {v.missing.join(" ; ")}</div>}
                </td>
                <td className="small">
                  <div>/ km : {v.cost_per_km ? money(v.cost_per_km, v.currency) : "—"}</div>
                  <div>/ heure : {v.cost_per_hour ? money(v.cost_per_hour, v.currency) : "—"}</div>
                  <div>/ tonne : {v.cost_per_tonne ? money(v.cost_per_tonne, v.currency) : "—"}</div>
                  <div>/ mission : {v.cost_per_mission ? money(v.cost_per_mission, v.currency) : "—"}</div>
                  <div className="muted">
                    {quantity(v.km, "km")} · {quantity(v.hours, "h")} · {quantity(v.tonnes, "t")} · {v.missions} mission(s)
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <h2>Par site</h2>
        <ul>
          {(report.data?.sites ?? []).map((s) => (
            <li key={s.site_id}>
              {siteCode.get(s.site_id) ?? s.site_id} — {money(s.total, null)} ({s.vehicles} engin(s)){" "}
              <Badge tone={STATUS_TONE[s.total_status]}>{STATUS_LABEL[s.total_status]}</Badge>
            </li>
          ))}
        </ul>
      </DataState>
      {selected && <VehicleHistory vehicle={selected} onClose={() => setSelected(null)} />}
      {can(me.grants, "cost.labour_rate.manage") && <LabourRates />}
    </section>
  );
}

function VehicleHistory({ vehicle, onClose }: { vehicle: VehicleCost; onClose: () => void }) {
  const history = useQuery({
    queryKey: ["vehicle-cost-history", vehicle.vehicle_id],
    queryFn: () =>
      call("get", "/costs/vehicles/{vehicle_id}/history", { path: { vehicle_id: vehicle.vehicle_id }, query: { months: 6 } }),
  });
  return (
    <section className="card" aria-label={`Évolution du coût de ${vehicle.fleet_number}`}>
      <div className="page-head">
        <h2>
          Évolution sur 6 mois — <Link to={`/vehicules/${vehicle.vehicle_id}`}>{vehicle.fleet_number}</Link>
        </h2>
        <button type="button" onClick={onClose}>
          Fermer
        </button>
      </div>
      <DataState loading={history.isLoading} error={history.error} empty={!history.data}>
        <table>
          <thead>
            <tr>
              <th scope="col">Mois</th>
              <th scope="col">Total</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {(history.data?.data.months ?? []).map((m) => (
              <tr key={m.month}>
                <td>{m.month}</td>
                <td>{m.cost ? money(m.cost.total, m.cost.currency) : "—"}</td>
                <td>{m.cost && <Badge tone={STATUS_TONE[m.cost.total_status]}>{STATUS_LABEL[m.cost.total_status]}</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}

function LabourRates() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { sites } = useSites();
  const [adding, setAdding] = useState(false);
  const rates = useQuery({ queryKey: ["labour-rates"], queryFn: () => read("/costs/labour-rates") });
  const [form, setForm] = useState({ site_id: "", hourly_rate: "", currency: "GNF", valid_from: "" });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  return (
    <section aria-label="Taux horaires de main-d'œuvre">
      <h2>Taux horaires de main-d'œuvre</h2>
      <p className="muted small">
        Sans taux en vigueur, la main-d'œuvre n'est pas valorisée. Un nouveau taux s'applique à partir de sa date d'effet ; le
        taux d'un site prime sur celui de la société.
      </p>
      <ul>
        {(rates.data ?? []).map((r: Schemas["LabourRateOut"]) => (
          <li key={r.maintenance_labour_rate_id}>
            {r.site_id ? siteCode.get(r.site_id) : "Société"} — {money(r.hourly_rate, r.currency)} / h depuis le {r.valid_from}
          </li>
        ))}
      </ul>
      {adding ? (
        <ActionForm
          title="Nouveau taux horaire"
          submitLabel="Enregistrer"
          onCancel={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            void queryClient.invalidateQueries({ queryKey: ["labour-rates"] });
            void queryClient.invalidateQueries({ queryKey: ["vehicle-costs"] });
          }}
          onSubmit={() =>
            call("post", "/costs/labour-rates", {
              body: {
                site_id: form.site_id || null,
                hourly_rate: form.hourly_rate,
                currency: form.currency.trim().toUpperCase(),
                valid_from: form.valid_from,
              },
            })
          }
        >
          <label>
            Portée
            <select value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
              {can(me.grants, "cost.labour_rate.manage") && <option value="">Toute la société</option>}
              {sites
                .filter((s) => can(me.grants, "cost.labour_rate.manage", s.site_id))
                .map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.code} — {s.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Taux horaire
            <input required type="number" min="0.01" step="0.01" value={form.hourly_rate} onChange={(e) => setForm({ ...form, hourly_rate: e.target.value })} />
          </label>
          <label>
            Devise
            <input required maxLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          </label>
          <label>
            Date d'effet
            <input required type="date" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
          </label>
        </ActionForm>
      ) : (
        <button type="button" onClick={() => setAdding(true)}>
          Ajouter un taux
        </button>
      )}
    </section>
  );
}
