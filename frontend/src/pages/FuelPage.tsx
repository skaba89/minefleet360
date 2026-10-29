import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import { Icon } from "../components/Icon";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Tank = Schemas["TankOut"];
type FuelIssue = Schemas["FuelIssueOut"];
type FuelType = Schemas["TankCreate"]["fuel_type"];
type MeterKind = NonNullable<FuelIssue["meter_kind"]>;
type FuelStocktake = Schemas["FuelStocktakeOut"];
const PAGE_SIZE = 50;
const FUEL_TYPES: Record<FuelType, string> = { DIESEL: "Gazole", PETROL: "Essence" };
const METER_KINDS: Record<MeterKind, string> = { ODOMETER: "Kilométrique (km)", HOUR_METER: "Horaire (h)" };
const ISSUE_STATUS: Record<FuelIssue["status"], string> = {
  PENDING_APPROVAL: "À approuver",
  APPROVED: "Approuvé",
  REJECTED: "Refusé",
};
const REJECT_REASONS = {
  WRONG_VEHICLE: "Véhicule incorrect",
  INVALID_QUANTITY: "Quantité à vérifier",
  OTHER: "Autre motif",
};
const STOCKTAKE_REASONS = {
  MEASUREMENT: "Mesure physique",
  LOSS: "Perte ou évaporation",
  DATA_CORRECTION: "Correction de saisie",
  OTHER: "Autre motif",
};
const ISSUE_TONE: Record<FuelIssue["status"], "ok" | "warn" | "bad" | "neutral"> = {
  PENDING_APPROVAL: "warn",
  APPROVED: "ok",
  REJECTED: "bad",
};

export function FuelPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, sites, timezoneOf } = useSites();
  const [tankPage, setTankPage] = useState(1);
  const [issuePage, setIssuePage] = useState(1);
  const [stocktakePage, setStocktakePage] = useState(1);
  const [issueStatus, setIssueStatus] = useState("");
  const [panel, setPanel] = useState<"tank" | "receipt" | "issue" | "stocktake" | "threshold" | null>(null);
  const [selectedTankId, setSelectedTankId] = useState("");
  const [rejectingIssue, setRejectingIssue] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<"WRONG_VEHICLE" | "INVALID_QUANTITY" | "OTHER">("OTHER");
  const [error, setError] = useState<unknown>(null);
  const canRead = can(me.grants, "fuel.stock.read", siteId);
  const canManage = can(me.grants, "fuel.stock.manage", siteId);
  const canReceive = can(me.grants, "fuel.stock.receive", siteId);
  const canRequest = can(me.grants, "fuel.issue.request", siteId);
  const canDecide = can(me.grants, "fuel.issue.decide", siteId);
  const canStocktake = can(me.grants, "fuel.stocktake.record", siteId);
  const canThreshold = can(me.grants, "fuel.stock.threshold", siteId);
  const tanks = useQuery({
    queryKey: ["fuel-tanks", siteId, tankPage],
    enabled: canRead,
    queryFn: () => read("/fuel/tanks", { query: { site_id: siteId, page: tankPage, page_size: PAGE_SIZE } }),
  });
  const issues = useQuery({
    queryKey: ["fuel-issues", siteId, issuePage, issueStatus],
    enabled: canRead,
    queryFn: () =>
      read("/fuel/issues", {
        query: {
          site_id: siteId,
          status: (issueStatus || null) as FuelIssue["status"] | null,
          page: issuePage,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const stocktakes = useQuery({
    queryKey: ["fuel-stocktakes", siteId, stocktakePage],
    enabled: canRead,
    queryFn: () => read("/fuel/stocktakes", { query: { site_id: siteId, page: stocktakePage, page_size: PAGE_SIZE } }),
  });
  const sitesById = new Map(sites.map((site) => [site.site_id, site.code]));
  const tankItems = tanks.data?.items ?? [];
  const issueItems = issues.data?.items ?? [];
  const refresh = async () => {
    setPanel(null);
    setError(null);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["fuel-tanks"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-issues"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-stocktakes"] }),
    ]);
  };
  const decide = async (issue: FuelIssue, decision: "APPROVED" | "REJECTED", reasonCode?: keyof typeof REJECT_REASONS) => {
    setError(null);
    try {
      await call("post", "/fuel/issues/{fuel_issue_id}/decision", {
        path: { fuel_issue_id: issue.fuel_issue_id },
        body: { decision, reason_code: decision === "REJECTED" ? reasonCode ?? "OTHER" : null },
      });
      setRejectingIssue(null);
      await refresh();
    } catch (err) {
      setError(err);
    }
  };

  if (!canRead && !canManage && !canReceive && !canRequest && !canDecide && !canStocktake && !canThreshold) {
    return <p>Vous n'avez pas accès à la gestion du carburant.</p>;
  }
  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Carburant</h1>
          <p className="muted">Stocks par cuve et ravitaillements des véhicules</p>
        </div>
        <Icon name="fuel" />
      </div>
      <div className="toolbar">
        {canManage && <button type="button" className="primary" onClick={() => setPanel("tank")}>Nouvelle cuve</button>}
        {canReceive && tankItems.length > 0 && <button type="button" onClick={() => setPanel("receipt")}>Enregistrer une réception</button>}
        {canRequest && tankItems.length > 0 && <button type="button" onClick={() => setPanel("issue")}>Demander un ravitaillement</button>}
        {canStocktake && tankItems.length > 0 && <button type="button" onClick={() => setPanel("stocktake")}>Faire un inventaire</button>}
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {panel === "tank" && <TankForm siteId={siteId} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "receipt" && <ReceiptForm tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "issue" && <IssueForm siteId={siteId} tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "stocktake" && <StocktakeForm tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "threshold" && <ThresholdForm tanks={tankItems} tankId={selectedTankId} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}

      <div className="card">
        <h2>Stocks disponibles</h2>
        <DataState loading={tanks.isLoading} error={tanks.error} empty={tankItems.length === 0} emptyText="Aucune cuve enregistrée pour ce périmètre.">
          <table>
            <thead><tr><th>Site</th><th>Cuve</th><th>Carburant</th><th>Capacité</th><th>En stock</th><th>Réservé</th><th>Disponible</th><th>Seuil</th><th>État</th>{canThreshold && <th>Action</th>}</tr></thead>
            <tbody>{tankItems.map((tank) => <tr key={tank.fuel_tank_id}>
              <td>{sitesById.get(tank.site_id) ?? "—"}</td><td>{tank.code}</td><td>{FUEL_TYPES[tank.fuel_type]}</td>
              <td>{liters(tank.capacity_liters)}</td><td>{liters(tank.balance_liters)}</td>
              <td>{liters(tank.reserved_liters)}</td><td><strong>{liters(tank.available_liters)}</strong></td>
              <td>{tank.low_stock_threshold_liters === null ? "Non configuré" : liters(tank.low_stock_threshold_liters)}</td>
              <td><Badge tone={tank.low_stock ? "warn" : "ok"}>{tank.low_stock ? "Stock bas" : "Normal"}</Badge></td>
              {canThreshold && <td><button type="button" onClick={() => { setSelectedTankId(tank.fuel_tank_id); setPanel("threshold"); }}>Modifier le seuil</button></td>}
            </tr>)}</tbody>
          </table>
          <Pager page={tankPage} pageSize={PAGE_SIZE} total={tanks.data?.total ?? 0} onPage={setTankPage} />
        </DataState>
      </div>

      <div className="card">
        <h2>Inventaires physiques récents</h2>
        <DataState loading={stocktakes.isLoading} error={stocktakes.error} empty={(stocktakes.data?.items.length ?? 0) === 0} emptyText="Aucun inventaire enregistré.">
          <table>
            <thead><tr><th>Date</th><th>Cuve</th><th>Référence</th><th>Journal</th><th>Compté</th><th>Écart</th><th>Motif</th></tr></thead>
            <tbody>{stocktakes.data?.items.map((entry: FuelStocktake) => <tr key={entry.fuel_stocktake_id}>
              <td>{formatDateTime(entry.occurred_at, timezoneOf(entry.site_id))}</td><td>{entry.tank_code}</td><td>{entry.reference}</td>
              <td>{liters(entry.expected_liters)}</td><td>{liters(entry.counted_liters)}</td>
              <td>{deltaLiters(entry.delta_liters)}</td><td>{STOCKTAKE_REASONS[entry.reason_code]}</td>
            </tr>)}</tbody>
          </table>
          <Pager page={stocktakePage} pageSize={PAGE_SIZE} total={stocktakes.data?.total ?? 0} onPage={setStocktakePage} />
        </DataState>
      </div>

      <div className="card">
        <div className="page-head"><h2>Demandes de ravitaillement</h2><label>Statut<select value={issueStatus} onChange={(e) => { setIssueStatus(e.target.value); setIssuePage(1); }}><Options map={ISSUE_STATUS} empty="Tous" /></select></label></div>
        <DataState loading={issues.isLoading} error={issues.error} empty={issueItems.length === 0} emptyText="Aucune demande de ravitaillement.">
          <table>
            <thead><tr><th>Date</th><th>Cuve</th><th>Véhicule</th><th>Conducteur</th><th>Quantité</th><th>Compteur</th><th>État</th><th>Décision</th></tr></thead>
            <tbody>{issueItems.map((issue) => <tr key={issue.fuel_issue_id}>
              <td>{formatDateTime(issue.requested_at, timezoneOf(issue.site_id))}</td>
              <td>{issue.tank_code}</td><td>{issue.vehicle_fleet_number}</td><td title={issue.driver_id}>{issue.driver_id.slice(0, 8)}</td>
              <td>{liters(issue.liters)}</td><td>{issue.meter_value === null ? "—" : `${issue.meter_value} ${issue.meter_kind === "ODOMETER" ? "km" : "h"}`}</td>
              <td><Badge tone={ISSUE_TONE[issue.status]}>{ISSUE_STATUS[issue.status]}</Badge></td>
              <td>{canDecide && issue.status === "PENDING_APPROVAL" && issue.requested_by !== me.user_account_id ? <div className="actions">
                <button type="button" onClick={() => void decide(issue, "APPROVED")}>Approuver</button>
                {rejectingIssue === issue.fuel_issue_id ? <>
                  <select aria-label="Motif du refus" value={rejectReason} onChange={(e) => setRejectReason(e.target.value as keyof typeof REJECT_REASONS)}><Options map={REJECT_REASONS} /></select>
                  <button type="button" className="danger" onClick={() => void decide(issue, "REJECTED", rejectReason)}>Confirmer le refus</button>
                  <button type="button" onClick={() => setRejectingIssue(null)}>Annuler</button>
                </> : <button type="button" className="danger" onClick={() => setRejectingIssue(issue.fuel_issue_id)}>Refuser</button>}
              </div> : issue.decided_at ? formatDateTime(issue.decided_at, timezoneOf(issue.site_id)) : "—"}</td>
            </tr>)}</tbody>
          </table>
          <Pager page={issuePage} pageSize={PAGE_SIZE} total={issues.data?.total ?? 0} onPage={setIssuePage} />
        </DataState>
      </div>
      <p className="muted small">Les demandes en attente réservent le stock. Une autre personne doit les approuver ; l'approbation enregistre la sortie au journal. Les relevés GPS ne remplacent pas une mesure de carburant.</p>
    </section>
  );
}

function TankForm({ siteId, onCancel, onDone }: { siteId: string | null; onCancel: () => void; onDone: () => void }) {
  const { sites } = useSites();
  const [site, setSite] = useState(siteId ?? sites[0]?.site_id ?? "");
  const [code, setCode] = useState("");
  const [type, setType] = useState<FuelType>("DIESEL");
  const [capacity, setCapacity] = useState("");
  const [threshold, setThreshold] = useState("");
  return <ActionForm title="Créer une cuve" submitLabel="Créer la cuve" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/tanks", { body: { site_id: site, code: code.trim(), fuel_type: type, capacity_liters: Number(capacity), low_stock_threshold_liters: threshold ? Number(threshold) : null } })}>
    <label>Site<select required value={site} onChange={(e) => setSite(e.target.value)}><option value="">Choisir un site</option>{sites.map((s) => <option key={s.site_id} value={s.site_id}>{s.code} — {s.name}</option>)}</select></label>
    <label>Code de cuve<input required maxLength={32} pattern="[A-Za-z0-9_-]{1,32}" value={code} onChange={(e) => setCode(e.target.value)} /></label>
    <label>Carburant<select value={type} onChange={(e) => setType(e.target.value as FuelType)}><Options map={FUEL_TYPES} /></select></label>
    <label>Capacité (L)<input required type="number" min="0.001" max="2000000" step="0.001" value={capacity} onChange={(e) => setCapacity(e.target.value)} /></label>
    <label>Seuil d'alerte bas (L)<input type="number" min="0.001" max={capacity || undefined} step="0.001" value={threshold} onChange={(e) => setThreshold(e.target.value)} /><span className="muted small">Laissez vide pour désactiver l'alerte.</span></label>
  </ActionForm>;
}

function ThresholdForm({ tanks, tankId, onCancel, onDone }: { tanks: Tank[]; tankId: string; onCancel: () => void; onDone: () => void }) {
  const [value, setValue] = useState(() => {
    const threshold = tanks.find((tank) => tank.fuel_tank_id === tankId)?.low_stock_threshold_liters;
    return threshold === null || threshold === undefined ? "" : String(threshold);
  });
  const tank = tanks.find((item) => item.fuel_tank_id === tankId);
  if (!tank) return null;
  return <ActionForm title={`Seuil d'alerte — cuve ${tank.code}`} submitLabel="Enregistrer le seuil" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/tanks/{fuel_tank_id}/threshold", { path: { fuel_tank_id: tankId }, body: { low_stock_threshold_liters: value.trim() ? Number(value) : null } })}>
    <label>Seuil bas (L)<input type="number" min="0.001" max={Number(tank.capacity_liters)} step="0.001" value={value} onChange={(e) => setValue(e.target.value)} /><span className="muted small">Une alerte s'affiche lorsque le stock atteint ce niveau ou passe en dessous.</span></label>
  </ActionForm>;
}

function StocktakeForm({ tanks, timezoneOf, onCancel, onDone }: { tanks: Tank[]; timezoneOf: (siteId: string | null | undefined) => string; onCancel: () => void; onDone: () => void }) {
  const [tankId, setTankId] = useState(tanks[0]?.fuel_tank_id ?? "");
  const tank = tanks.find((item) => item.fuel_tank_id === tankId);
  const [counted, setCounted] = useState("");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState<keyof typeof STOCKTAKE_REASONS>("MEASUREMENT");
  const [date, setDate] = useState(utcToZonedInput(new Date(), timezoneOf(tank?.site_id)));
  return <ActionForm title="Inventaire physique de carburant" submitLabel="Enregistrer l'inventaire" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/tanks/{fuel_tank_id}/stocktakes", { path: { fuel_tank_id: tankId }, body: { counted_liters: Number(counted), reference: reference.trim(), reason_code: reason, occurred_at: zonedInputToUtc(date, timezoneOf(tank?.site_id)).toISOString() } })}>
    <label>Cuve<select required value={tankId} onChange={(e) => setTankId(e.target.value)}>{tanks.map((item) => <option key={item.fuel_tank_id} value={item.fuel_tank_id}>{item.code} · {FUEL_TYPES[item.fuel_type]}</option>)}</select></label>
    <p className="muted">Stock attendu au dernier mouvement : {tank ? liters(tank.balance_liters) : "—"}. Les demandes en attente doivent rester couvertes par le comptage.</p>
    <label>Quantité réellement comptée (L)<input required type="number" min="0" max={tank ? Number(tank.capacity_liters) : 2000000} step="0.001" value={counted} onChange={(e) => setCounted(e.target.value)} /></label>
    <label>Référence du relevé<input required maxLength={60} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
    <label>Motif<select value={reason} onChange={(e) => setReason(e.target.value as keyof typeof STOCKTAKE_REASONS)}><Options map={STOCKTAKE_REASONS} /></select></label>
    <label>Date du comptage<input required type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>
  </ActionForm>;
}

function ReceiptForm({ tanks, timezoneOf, onCancel, onDone }: { tanks: Tank[]; timezoneOf: (siteId: string | null | undefined) => string; onCancel: () => void; onDone: () => void }) {
  const [tankId, setTankId] = useState(tanks[0]?.fuel_tank_id ?? "");
  const selected = tanks.find((tank) => tank.fuel_tank_id === tankId);
  const [litersValue, setLitersValue] = useState("");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState(utcToZonedInput(new Date(), timezoneOf(selected?.site_id)));
  return <ActionForm title="Réception de carburant" submitLabel="Enregistrer la réception" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/tanks/{fuel_tank_id}/receipts", { path: { fuel_tank_id: tankId }, body: { liters: Number(litersValue), reference: reference.trim(), occurred_at: zonedInputToUtc(date, timezoneOf(selected?.site_id)).toISOString() } })}>
    <label>Cuve<select required value={tankId} onChange={(e) => setTankId(e.target.value)}>{tanks.map((tank) => <option key={tank.fuel_tank_id} value={tank.fuel_tank_id}>{tank.code} · {FUEL_TYPES[tank.fuel_type]}</option>)}</select></label>
    <label>Quantité reçue (L)<input required type="number" min="0.001" max="2000000" step="0.001" value={litersValue} onChange={(e) => setLitersValue(e.target.value)} /></label>
    <label>Référence du bon de livraison<input required maxLength={60} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
    <label>Date de réception<input required type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>
  </ActionForm>;
}

function IssueForm({ siteId, tanks, timezoneOf, onCancel, onDone }: { siteId: string | null; tanks: Tank[]; timezoneOf: (siteId: string | null | undefined) => string; onCancel: () => void; onDone: () => void }) {
  const assignments = useQuery({
    queryKey: ["fuel-active-assignments", siteId],
    queryFn: () => read("/vehicle-assignments", { query: { site_id: siteId, status: "ACTIVE", page_size: 200 } }),
  });
  const activeAssignments = assignments.data?.items.filter((assignment) => assignment.status === "ACTIVE") ?? [];
  const [tankId, setTankId] = useState(tanks[0]?.fuel_tank_id ?? "");
  const [assignmentId, setAssignmentId] = useState("");
  const [litersValue, setLitersValue] = useState("");
  const [meterKind, setMeterKind] = useState<"" | MeterKind>("");
  const [meterValue, setMeterValue] = useState("");
  const [date, setDate] = useState(utcToZonedInput(new Date(), timezoneOf(tanks[0]?.site_id)));
  const selectedTank = tanks.find((tank) => tank.fuel_tank_id === tankId);
  const assignment = activeAssignments.find((item) => item.vehicle_assignment_id === assignmentId);
  return <ActionForm title="Demande de ravitaillement" submitLabel="Enregistrer la demande" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/issues", { body: {
    fuel_tank_id: tankId,
    vehicle_id: assignment?.vehicle_id ?? "",
    driver_id: assignment?.driver_id ?? "",
    liters: Number(litersValue),
    meter_kind: meterKind || null,
    meter_value: meterValue ? Number(meterValue) : null,
    requested_at: zonedInputToUtc(date, timezoneOf(selectedTank?.site_id)).toISOString(),
  } })}>
    <label>Cuve<select required value={tankId} onChange={(e) => setTankId(e.target.value)}>{tanks.map((tank) => <option key={tank.fuel_tank_id} value={tank.fuel_tank_id}>{tank.code} · {FUEL_TYPES[tank.fuel_type]} · {liters(tank.available_liters)} disponible</option>)}</select></label>
    <label>Véhicule et conducteur<select required value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}><option value="">Choisir une affectation active</option>{activeAssignments.map((item) => <option key={item.vehicle_assignment_id} value={item.vehicle_assignment_id}>{item.vehicle_fleet_number} — {item.driver_display_name}</option>)}</select></label>
    <DataState loading={assignments.isLoading} error={assignments.error} empty={activeAssignments.length === 0} emptyText="Aucune affectation active disponible sur ce site."><span className="muted small">Le serveur vérifiera à nouveau l'affectation au moment de l'enregistrement.</span></DataState>
    <label>Quantité demandée (L)<input required type="number" min="0.001" max="100000" step="0.001" value={litersValue} onChange={(e) => setLitersValue(e.target.value)} /></label>
    <label>Compteur (si disponible)<select value={meterKind} onChange={(e) => setMeterKind(e.target.value as "" | MeterKind)}><option value="">Non renseigné</option><Options map={METER_KINDS} /></select></label>
    {meterKind && <label>Valeur ({meterKind === "ODOMETER" ? "km" : "h"})<input required type="number" min="0" step="0.1" value={meterValue} onChange={(e) => setMeterValue(e.target.value)} /></label>}
    <label>Date de la demande<input required type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>
  </ActionForm>;
}

function liters(value: string): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(Number(value))} L`;
}

function deltaLiters(value: string): string {
  const formatted = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3, signDisplay: "always" }).format(Number(value));
  return `${formatted} L`;
}
