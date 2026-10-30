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
type Pump = Schemas["FuelPumpOut"];
type PumpReconciliation = Schemas["FuelPumpReconciliationOut"];
type AnomalyCase = Schemas["AnomalyCaseOut"];
type AnomalyStatus = AnomalyCase["status"];
type AnomalyEvent = Schemas["AnomalyEventOut"];
type FuelIssue = Schemas["FuelIssueOut"];
type FuelType = Schemas["TankCreate"]["fuel_type"];
type MeterKind = NonNullable<FuelIssue["meter_kind"]>;
type FuelStocktake = Schemas["FuelStocktakeOut"];
type FuelStockAlert = Schemas["FuelStockAlertOut"];
type Consumption = Schemas["FuelConsumptionOut"];
type FuelSupplier = Schemas["FuelSupplierOut"];
type FuelPurchase = Schemas["FuelPurchaseOrderOut"];
type PurchaseStatus = FuelPurchase["status"];
type Currency = Schemas["PurchaseCreate"]["currency"];
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
const PURCHASE_STATUS: Record<PurchaseStatus, string> = {
  PENDING_APPROVAL: "À approuver",
  REJECTED: "Refusée",
  APPROVED: "Approuvée",
  PARTIALLY_RECEIVED: "Livraison partielle",
  RECEIVED: "Réceptionnée",
};
const PURCHASE_TONE: Record<PurchaseStatus, "ok" | "warn" | "bad" | "neutral"> = {
  PENDING_APPROVAL: "warn",
  REJECTED: "bad",
  APPROVED: "ok",
  PARTIALLY_RECEIVED: "warn",
  RECEIVED: "neutral",
};
const PURCHASE_REJECT_REASONS = {
  BUDGET: "Budget non validé",
  SUPPLIER: "Fournisseur à revoir",
  QUANTITY: "Quantité à revoir",
  OTHER: "Autre motif",
};
const CURRENCIES = { GNF: "GNF", USD: "USD", EUR: "EUR" };

export function FuelPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, sites, timezoneOf } = useSites();
  const [tankPage, setTankPage] = useState(1);
  const [selectedPumpId, setSelectedPumpId] = useState("");
  const [selectedAnomalyCaseId, setSelectedAnomalyCaseId] = useState("");
  const [anomalyCasePage, setAnomalyCasePage] = useState(1);
  const [anomalyStatusFilter, setAnomalyStatusFilter] = useState<"ALL" | AnomalyStatus>("ALL");
  const [anomalyEventPage, setAnomalyEventPage] = useState(1);
  const [anomalyJustification, setAnomalyJustification] = useState("");
  const [anomalySaving, setAnomalySaving] = useState(false);
  const [meterValue, setMeterValue] = useState("");
  const [meterReference, setMeterReference] = useState("");
  const [meterSaving, setMeterSaving] = useState(false);
  const [pumpPage, setPumpPage] = useState(1);
  const [pumpToleranceLiters, setPumpToleranceLiters] = useState("5");
  const [pumpTolerancePercent, setPumpTolerancePercent] = useState("1");
  const [pumpToleranceSaving, setPumpToleranceSaving] = useState(false);
  const [anomalyOpeningId, setAnomalyOpeningId] = useState<string | null>(null);
  const [pumpOnlyAnomalies, setPumpOnlyAnomalies] = useState(false);
  const [issuePage, setIssuePage] = useState(1);
  const [consumptionPage, setConsumptionPage] = useState(1);
  const [vehicleId, setVehicleId] = useState("");
  const [consumptionMeter, setConsumptionMeter] = useState<"" | MeterKind>("");
  const [stocktakePage, setStocktakePage] = useState(1);
  const [purchasePage, setPurchasePage] = useState(1);
  const [purchaseStatus, setPurchaseStatus] = useState("");
  const [issueStatus, setIssueStatus] = useState("");
  const [panel, setPanel] = useState<"tank" | "receipt" | "issue" | "stocktake" | "threshold" | "supplier" | "purchase" | "purchase-receipt" | "pump" | null>(null);
  const [selectedTankId, setSelectedTankId] = useState("");
  const [rejectingIssue, setRejectingIssue] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<"WRONG_VEHICLE" | "INVALID_QUANTITY" | "OTHER">("OTHER");
  const [selectedPurchaseId, setSelectedPurchaseId] = useState("");
  const [rejectingPurchase, setRejectingPurchase] = useState<string | null>(null);
  const [purchaseRejectReason, setPurchaseRejectReason] = useState<keyof typeof PURCHASE_REJECT_REASONS>("OTHER");
  const [error, setError] = useState<unknown>(null);
  const canRead = can(me.grants, "fuel.stock.read", siteId);
  const canReadAnomalies = can(me.grants, "fuel.anomaly.read", siteId);
  const canManageAnomalies = can(me.grants, "fuel.anomaly.manage", siteId);
  const canManagePumps = can(me.grants, "fuel.pump.manage", siteId);
  const canRecordPumpMeter = can(me.grants, "fuel.meter.record", siteId);
  const canManage = can(me.grants, "fuel.stock.manage", siteId);
  const canReceive = can(me.grants, "fuel.stock.receive", siteId);
  const canRequest = can(me.grants, "fuel.issue.request", siteId);
  const canDecide = can(me.grants, "fuel.issue.decide", siteId);
  const canStocktake = can(me.grants, "fuel.stocktake.record", siteId);
  const canThreshold = can(me.grants, "fuel.stock.threshold", siteId);
  const canAcknowledgeAlert = can(me.grants, "fuel.alert.acknowledge", siteId);
  const canReadPurchases = can(me.grants, "fuel.purchase.read", siteId);
  const canManageSuppliers = can(me.grants, "fuel.supplier.manage", siteId);
  const canCreatePurchase = can(me.grants, "fuel.purchase.create", siteId);
  const canDecidePurchase = can(me.grants, "fuel.purchase.decide", siteId);
  const canReceivePurchase = can(me.grants, "fuel.purchase.receive", siteId);
  const anomalyCases = useQuery({
    queryKey: ["fuel-anomaly-cases", siteId, anomalyCasePage, anomalyStatusFilter],
    enabled: canReadAnomalies,
    queryFn: () => read("/fuel/anomaly-cases", {
      query: {
        site_id: siteId,
        status: anomalyStatusFilter === "ALL" ? null : anomalyStatusFilter,
        page: anomalyCasePage,
        page_size: PAGE_SIZE,
      },
    }),
  });
  const anomalyEvents = useQuery({
    queryKey: ["fuel-anomaly-events", selectedAnomalyCaseId, anomalyEventPage],
    enabled: canReadAnomalies && Boolean(selectedAnomalyCaseId),
    queryFn: () => read("/fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events", {
      path: { fuel_pump_anomaly_case_id: selectedAnomalyCaseId }, query: { page: anomalyEventPage, page_size: PAGE_SIZE },
    }),
  });
  const nextAnomalyEvent = (() => {
    if (anomalyEvents.isLoading || anomalyEvents.isFetching) return null;
    if ((anomalyEvents.data?.total ?? 0) > (anomalyEvents.data?.items.length ?? 0)) return null;
    const events = anomalyEvents.data?.items ?? [];
    const last = events[events.length - 1];
    if (!last) return "ACKNOWLEDGED" as const;
    if (last.event_type === "ACKNOWLEDGED") return "JUSTIFIED" as const;
    if (last.event_type === "JUSTIFIED") return "CLOSED" as const;
    return null;
  })();
  const submitAnomalyEvent = async () => {
    if (!selectedAnomalyCaseId || !nextAnomalyEvent || anomalyJustification.trim().length < 10) return;
    setAnomalySaving(true);
    setError(null);
    try {
      await call("post", "/fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events", {
        path: { fuel_pump_anomaly_case_id: selectedAnomalyCaseId },
        body: { event_type: nextAnomalyEvent, justification: anomalyJustification.trim() },
      });
      setAnomalyJustification("");
      setAnomalyEventPage(1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fuel-anomaly-events", selectedAnomalyCaseId] }),
        queryClient.invalidateQueries({ queryKey: ["fuel-anomaly-cases"] }),
      ]);
    } catch (err) { setError(err); } finally { setAnomalySaving(false); }
  };
  const pumps = useQuery({
    queryKey: ["fuel-pumps", siteId],
    enabled: canRead,
    queryFn: () => read("/fuel/pumps", { query: { site_id: siteId, page: 1, page_size: 200 } }),
  });
  const pumpReconciliations = useQuery({
    queryKey: ["fuel-pump-reconciliations", selectedPumpId, pumpPage],
    enabled: canRead && Boolean(selectedPumpId),
    queryFn: () => read("/fuel/pumps/{fuel_pump_id}/reconciliations", {
      path: { fuel_pump_id: selectedPumpId },
      query: { page: pumpPage, page_size: PAGE_SIZE },
    }),
  });
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
  const alerts = useQuery({
    queryKey: ["fuel-stock-alerts", siteId],
    enabled: canRead,
    queryFn: () => read("/fuel/alerts", { query: { site_id: siteId, active_only: true, page: 1, page_size: 50 } }),
  });
  const suppliers = useQuery({
    queryKey: ["fuel-suppliers", siteId],
    enabled: canReadPurchases,
    queryFn: () => read("/fuel/suppliers", { query: { site_id: siteId, page: 1, page_size: 200 } }),
  });
  const purchases = useQuery({
    queryKey: ["fuel-purchases", siteId, purchasePage, purchaseStatus],
    enabled: canReadPurchases,
    queryFn: () => read("/fuel/purchases", { query: { site_id: siteId, status: (purchaseStatus || null) as PurchaseStatus | null, page: purchasePage, page_size: PAGE_SIZE } }),
  });
  const vehicles = useQuery({
    queryKey: ["fuel-consumption-vehicles", siteId],
    enabled: canRead,
    queryFn: () => read("/vehicles", { query: { site_id: siteId, page: 1, page_size: 200 } }),
  });
  const consumption = useQuery({
    queryKey: ["fuel-consumption", vehicleId, consumptionPage, consumptionMeter],
    enabled: canRead && Boolean(vehicleId),
    queryFn: () => read("/fuel/vehicles/{vehicle_id}/consumption", {
      path: { vehicle_id: vehicleId },
      query: { page: consumptionPage, page_size: PAGE_SIZE, meter_kind: consumptionMeter || null },
    }),
  });
  const sitesById = new Map(sites.map((site) => [site.site_id, site.code]));
  const tankItems = tanks.data?.items ?? [];
  const issueItems = issues.data?.items ?? [];
  const supplierItems = suppliers.data?.items ?? [];
  const purchaseItems = purchases.data?.items ?? [];
  const selectedPump = pumps.data?.items.find((pump: Pump) => pump.fuel_pump_id === selectedPumpId);
  const submitPumpReading = async () => {
    if (!selectedPumpId || !meterReference.trim() || meterValue.trim() === "") return;
    setMeterSaving(true);
    setError(null);
    try {
      await call("post", "/fuel/pumps/{fuel_pump_id}/meter-readings", {
        path: { fuel_pump_id: selectedPumpId },
        body: { cumulative_liters: meterValue, measured_at: new Date().toISOString(), source: "MANUAL", source_reference: meterReference.trim() },
      });
      setMeterValue("");
      setMeterReference("");
      await queryClient.invalidateQueries({ queryKey: ["fuel-pump-reconciliations", selectedPumpId] });
    } catch (err) {
      setError(err);
    } finally {
      setMeterSaving(false);
    }
  };
  const savePumpTolerance = async () => {
    if (!selectedPumpId || pumpToleranceLiters === "" || pumpTolerancePercent === "") return;
    setPumpToleranceSaving(true);
    setError(null);
    try {
      await call("put", "/fuel/pumps/{fuel_pump_id}/anomaly-tolerance", {
        path: { fuel_pump_id: selectedPumpId },
        body: { tolerance_liters: pumpToleranceLiters, tolerance_percent: pumpTolerancePercent },
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fuel-pumps"] }),
        queryClient.invalidateQueries({ queryKey: ["fuel-pump-reconciliations", selectedPumpId] }),
      ]);
    } catch (err) { setError(err); } finally { setPumpToleranceSaving(false); }
  };
  const openAnomalyCase = async (item: PumpReconciliation) => {
    setAnomalyOpeningId(item.end_reading_id);
    setError(null);
    try {
      await call("post", "/fuel/pumps/{fuel_pump_id}/anomaly-cases", {
        path: { fuel_pump_id: item.fuel_pump_id },
        body: { start_reading_id: item.start_reading_id, end_reading_id: item.end_reading_id },
      });
      await queryClient.invalidateQueries({ queryKey: ["fuel-anomaly-cases"] });
    } catch (err) { setError(err); } finally { setAnomalyOpeningId(null); }
  };
  const refresh = async () => {
    setPanel(null);
    setError(null);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["fuel-tanks"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-pumps"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-issues"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-stocktakes"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-stock-alerts"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-suppliers"] }),
      queryClient.invalidateQueries({ queryKey: ["fuel-purchases"] }),
    ]);
  };
  const decidePurchase = async (purchase: FuelPurchase, decision: "APPROVED" | "REJECTED", reasonCode?: keyof typeof PURCHASE_REJECT_REASONS) => {
    setError(null);
    try {
      await call("post", "/fuel/purchases/{fuel_purchase_order_id}/decision", {
        path: { fuel_purchase_order_id: purchase.fuel_purchase_order_id },
        body: { decision, reason_code: decision === "REJECTED" ? reasonCode ?? "OTHER" : null },
      });
      setRejectingPurchase(null);
      await refresh();
    } catch (err) {
      setError(err);
    }
  };
  const acknowledgeAlert = async (alert: FuelStockAlert) => {
    setError(null);
    try {
      await call("post", "/fuel/alerts/{fuel_stock_alert_id}/acknowledge", {
        path: { fuel_stock_alert_id: alert.fuel_stock_alert_id },
      });
      await queryClient.invalidateQueries({ queryKey: ["fuel-stock-alerts"] });
    } catch (err) {
      setError(err);
    }
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

  if (!canRead && !canManage && !canReceive && !canRequest && !canDecide && !canStocktake && !canThreshold && !canReadPurchases && !canManageSuppliers && !canCreatePurchase && !canDecidePurchase && !canReceivePurchase) {
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
        {canManagePumps && tankItems.length > 0 && <button type="button" onClick={() => setPanel("pump")}>Nouvelle pompe</button>}
        {canReceive && tankItems.length > 0 && <button type="button" onClick={() => setPanel("receipt")}>Enregistrer une réception</button>}
        {canRequest && tankItems.length > 0 && <button type="button" onClick={() => setPanel("issue")}>Demander un ravitaillement</button>}
        {canStocktake && tankItems.length > 0 && <button type="button" onClick={() => setPanel("stocktake")}>Faire un inventaire</button>}
        {canManageSuppliers && <button type="button" onClick={() => setPanel("supplier")}>Nouveau fournisseur</button>}
        {canCreatePurchase && tankItems.length > 0 && supplierItems.length > 0 && <button type="button" onClick={() => setPanel("purchase")}>Nouvelle commande</button>}
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {panel === "pump" && <PumpCreateForm tanks={tankItems} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "tank" && <TankForm siteId={siteId} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "receipt" && <ReceiptForm tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "issue" && <IssueForm siteId={siteId} tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "stocktake" && <StocktakeForm tanks={tankItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "threshold" && <ThresholdForm tanks={tankItems} tankId={selectedTankId} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "supplier" && <SupplierForm siteId={siteId} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "purchase" && <PurchaseForm tanks={tankItems} suppliers={supplierItems} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}
      {panel === "purchase-receipt" && <PurchaseReceiptForm purchase={purchaseItems.find((item) => item.fuel_purchase_order_id === selectedPurchaseId)} timezoneOf={timezoneOf} onCancel={() => setPanel(null)} onDone={() => void refresh()} />}

      <div className="card">
        <div className="page-head"><div><h2>Pompes et rapprochements</h2><p className="muted">Volumes issus des compteurs, rapprochés des ravitaillements approuvés.</p></div></div>
        <DataState loading={pumps.isLoading} error={pumps.error} empty={(pumps.data?.items.length ?? 0) === 0} emptyText="Aucune pompe pour ce périmètre.">
          <label>Pompe<select aria-label="Pompe à contrôler" value={selectedPumpId} onChange={(event) => {
            const pump = pumps.data?.items.find((item: Pump) => item.fuel_pump_id === event.target.value);
            setSelectedPumpId(event.target.value); setPumpPage(1);
            setPumpToleranceLiters(pump?.anomaly_tolerance_liters ?? "5");
            setPumpTolerancePercent(pump?.anomaly_tolerance_percent ?? "1");
          }}><option value="">Sélectionner une pompe</option>{pumps.data?.items.map((pump: Pump) => <option key={pump.fuel_pump_id} value={pump.fuel_pump_id}>{pump.code} — {pump.name} · {pump.tank_code}</option>)}</select></label>
        </DataState>
        {selectedPumpId && <div className="toolbar" aria-label="Paramètres de rapprochement">
          <label>Tolérance (L)<input type="number" min="0" max="1000" step="0.001" disabled={!canManagePumps} value={pumpToleranceLiters} onChange={(event) => setPumpToleranceLiters(event.target.value)} /></label>
          <label>Tolérance (%)<input type="number" min="0" max="100" step="0.001" disabled={!canManagePumps} value={pumpTolerancePercent} onChange={(event) => setPumpTolerancePercent(event.target.value)} /></label>
          {canManagePumps && <button type="button" disabled={pumpToleranceSaving || !selectedPump || pumpToleranceLiters === "" || pumpTolerancePercent === ""} onClick={() => void savePumpTolerance()}>{pumpToleranceSaving ? "Enregistrement…" : "Enregistrer les tolérances"}</button>}
          <label><input type="checkbox" checked={pumpOnlyAnomalies} onChange={(event) => setPumpOnlyAnomalies(event.target.checked)} /> Afficher uniquement les anomalies sur cette page</label>
        </div>}
        {selectedPumpId && <p className="muted small">Ces seuils sont enregistrés sur la pompe et appliqués par le serveur lors de l’ouverture d’un dossier.</p>}
        {selectedPumpId && canRecordPumpMeter && <form aria-label="Nouveau relevé de pompe" onSubmit={(event) => { event.preventDefault(); void submitPumpReading(); }} className="toolbar">
          <label>Compteur cumulé (L)<input aria-label="Compteur cumulé (L)" type="number" min="0" step="0.001" required value={meterValue} onChange={(event) => setMeterValue(event.target.value)} /></label>
          <label>Référence de relevé<input aria-label="Référence de relevé" required maxLength={80} pattern="[A-Za-z0-9/_ .:-]{1,80}" value={meterReference} onChange={(event) => setMeterReference(event.target.value)} /></label>
          <button type="submit" disabled={meterSaving}>{meterSaving ? "Enregistrement…" : "Enregistrer le relevé"}</button>
        </form>}
        {selectedPumpId && <DataState loading={pumpReconciliations.isLoading} error={pumpReconciliations.error} empty={(pumpReconciliations.data?.items.length ?? 0) === 0} emptyText="Aucun intervalle de rapprochement. Deux relevés sont nécessaires.">
          <table><thead><tr><th>Début</th><th>Fin</th><th>Compteur</th><th>Sorties approuvées</th><th>Écart</th><th>Analyse</th>{canManageAnomalies && <th>Action</th>}</tr></thead><tbody>
            {pumpReconciliations.data?.items.filter((item: PumpReconciliation) => !pumpOnlyAnomalies || item.is_anomaly).map((item: PumpReconciliation) => <tr key={item.end_reading_id}>
              <td>{formatDateTime(item.interval_start_at, timezoneOf(pumps.data?.items.find((pump: Pump) => pump.fuel_pump_id === item.fuel_pump_id)?.site_id))}</td>
              <td>{formatDateTime(item.interval_end_at, timezoneOf(pumps.data?.items.find((pump: Pump) => pump.fuel_pump_id === item.fuel_pump_id)?.site_id))}</td>
              <td>{liters(item.meter_delta_liters)}</td><td>{liters(item.approved_issue_liters)}</td>
              <td>{deltaLiters(item.variance_liters)} ({number(item.variance_percent)} %)</td>
              <td><Badge tone={item.is_anomaly ? "warn" : "ok"}>{item.is_anomaly ? "Écart à examiner" : "Dans la tolérance"}</Badge></td>
              {canManageAnomalies && <td>{item.is_anomaly ? <button type="button" disabled={anomalyOpeningId === item.end_reading_id} onClick={() => void openAnomalyCase(item)}>{anomalyOpeningId === item.end_reading_id ? "Ouverture…" : "Ouvrir un dossier"}</button> : "—"}</td>}
            </tr>)}
          </tbody></table><Pager page={pumpPage} pageSize={PAGE_SIZE} total={pumpReconciliations.data?.total ?? 0} onPage={setPumpPage} />
        </DataState>}
      </div>

      {canReadAnomalies && <div className="card">
        <div className="page-head"><div><h2>Dossiers d’anomalies des pompes</h2><p className="muted">Dossiers et événements tracés par les responsables habilités.</p></div></div>
        <label>Statut<select aria-label="Filtrer les dossiers par statut" value={anomalyStatusFilter} onChange={(event) => { setAnomalyStatusFilter(event.target.value as "ALL" | AnomalyStatus); setAnomalyCasePage(1); setSelectedAnomalyCaseId(""); }}>
          <option value="ALL">Tous les statuts</option><option value="OPEN">Ouverts</option><option value="ACKNOWLEDGED">Pris en charge</option><option value="JUSTIFIED">Justifiés</option><option value="CLOSED">Clôturés</option>
        </select></label>
        <DataState loading={anomalyCases.isLoading} error={anomalyCases.error} empty={(anomalyCases.data?.items.length ?? 0) === 0} emptyText="Aucun dossier d’anomalie enregistré.">
          <table><thead><tr><th>Pompe</th><th>Statut</th><th>Qualification</th><th>Intervalle de relevés</th><th>Créateur</th><th>Historique</th></tr></thead><tbody>
            {anomalyCases.data?.items.map((entry: AnomalyCase) => <tr key={entry.fuel_pump_anomaly_case_id}>
              <td>{pumps.data?.items.find((pump: Pump) => pump.fuel_pump_id === entry.fuel_pump_id)?.code ?? entry.fuel_pump_id.slice(0, 8)}</td>
              <td>{entry.status === "OPEN" ? "Ouvert" : entry.status === "ACKNOWLEDGED" ? "Pris en charge" : entry.status === "JUSTIFIED" ? "Justifié" : "Clôturé"}</td>
              <td>{entry.variance_liters === null ? "Dossier historique" : <><strong>{deltaLiters(entry.variance_liters)}</strong> ({number(entry.variance_percent ?? "0")} %)<br /><span className="muted small">Seuils {liters(entry.tolerance_liters ?? "0")} / {number(entry.tolerance_percent ?? "0")} %</span></>}</td>
              <td title={entry.start_reading_id + " → " + entry.end_reading_id}>{entry.start_reading_id.slice(0, 8)} → {entry.end_reading_id.slice(0, 8)}</td>
              <td title={entry.created_by}>{entry.created_by.slice(0, 8)}</td>
              <td><button type="button" onClick={() => { setSelectedAnomalyCaseId(entry.fuel_pump_anomaly_case_id); setAnomalyEventPage(1); setAnomalyJustification(""); }}>Consulter</button></td>
            </tr>)}
          </tbody></table>
          <Pager page={anomalyCasePage} pageSize={PAGE_SIZE} total={anomalyCases.data?.total ?? 0} onPage={setAnomalyCasePage} />
        </DataState>
        {selectedAnomalyCaseId && <div><h3>Historique du dossier</h3>
          {canManageAnomalies && !anomalyEvents.isLoading && !anomalyEvents.error && nextAnomalyEvent &&
            !(nextAnomalyEvent === "CLOSED" && anomalyCases.data?.items.some((entry: AnomalyCase) => entry.fuel_pump_anomaly_case_id === selectedAnomalyCaseId && entry.created_by === me.user_account_id)) &&
            <form className="toolbar" aria-label="Traiter une anomalie" onSubmit={(event) => { event.preventDefault(); void submitAnomalyEvent(); }}>
              <label>Justification<textarea required minLength={10} maxLength={2000} value={anomalyJustification} onChange={(event) => setAnomalyJustification(event.target.value)} /></label>
              <button type="submit" disabled={anomalySaving || anomalyJustification.trim().length < 10}>{anomalySaving ? "Enregistrement…" : nextAnomalyEvent === "ACKNOWLEDGED" ? "Prendre en charge" : nextAnomalyEvent === "JUSTIFIED" ? "Justifier" : "Clôturer"}</button>
            </form>}
          <DataState loading={anomalyEvents.isLoading} error={anomalyEvents.error} empty={(anomalyEvents.data?.items.length ?? 0) === 0} emptyText="Dossier ouvert, aucun événement de traitement.">
            <table><thead><tr><th>Étape</th><th>Justification</th><th>Responsable</th></tr></thead><tbody>
              {anomalyEvents.data?.items.map((event: AnomalyEvent) => <tr key={event.fuel_pump_anomaly_event_id}>
                <td>{event.event_type}</td><td>{event.justification}</td><td title={event.actor_user_id}>{event.actor_user_id.slice(0, 8)}</td>
              </tr>)}
            </tbody></table>
            <Pager page={anomalyEventPage} pageSize={PAGE_SIZE} total={anomalyEvents.data?.total ?? 0} onPage={setAnomalyEventPage} />
          </DataState>
        </div>}
      </div>}

      <div className="card">
        <div className="page-head"><div><h2>Alertes de stock bas</h2><p className="muted">Une alerte reste active jusqu'au retour de la cuve au-dessus de son seuil.</p></div>
          {(alerts.data?.total ?? 0) > 0 && <Badge tone="warn">{alerts.data?.total} active{alerts.data?.total === 1 ? "" : "s"}</Badge>}
        </div>
        <DataState loading={alerts.isLoading} error={alerts.error} empty={(alerts.data?.items.length ?? 0) === 0} emptyText="Aucune alerte de stock bas active.">
          <table><thead><tr><th>Déclenchement</th><th>Site</th><th>Cuve</th><th>Carburant</th><th>Stock constaté</th><th>Seuil</th><th>Traitement</th></tr></thead>
            <tbody>{alerts.data?.items.map((alert: FuelStockAlert) => <tr key={alert.fuel_stock_alert_id}>
              <td>{formatDateTime(alert.triggered_at, timezoneOf(alert.site_id))}</td><td>{sitesById.get(alert.site_id) ?? "—"}</td><td>{alert.tank_code}</td><td>{FUEL_TYPES[alert.fuel_type]}</td>
              <td><strong>{liters(alert.balance_liters)}</strong></td><td>{liters(alert.threshold_liters)}</td>
              <td>{alert.acknowledged_at ? <Badge tone="neutral">Prise en compte</Badge> : canAcknowledgeAlert ? <button type="button" onClick={() => void acknowledgeAlert(alert)}>Prendre en compte</button> : <Badge tone="warn">À traiter</Badge>}</td>
            </tr>)}</tbody>
          </table>
        </DataState>
      </div>

      {canReadPurchases && <div className="card">
        <div className="page-head"><div><h2>Achats de carburant</h2><p className="muted">Commandes fournisseurs approuvées séparément avant leur réception en cuve.</p></div>
          <label>Statut<select value={purchaseStatus} onChange={(e) => { setPurchaseStatus(e.target.value); setPurchasePage(1); }}><Options map={PURCHASE_STATUS} empty="Tous" /></select></label>
        </div>
        <DataState loading={purchases.isLoading} error={purchases.error} empty={purchaseItems.length === 0} emptyText="Aucune commande fournisseur pour ce périmètre.">
          <table><thead><tr><th>Date</th><th>Référence</th><th>Fournisseur</th><th>Cuve</th><th>Commandé</th><th>Reçu</th><th>Montant</th><th>État</th><th>Actions</th></tr></thead>
            <tbody>{purchaseItems.map((purchase) => <tr key={purchase.fuel_purchase_order_id}>
              <td>{formatDateTime(purchase.ordered_at, timezoneOf(purchase.site_id))}</td><td>{purchase.reference}</td><td>{purchase.supplier_name}</td><td>{purchase.tank_code}</td>
              <td>{liters(purchase.quantity_liters)}</td><td>{liters(purchase.received_liters)}</td><td>{money(purchase.total_amount, purchase.currency)}</td>
              <td><Badge tone={PURCHASE_TONE[purchase.status]}>{PURCHASE_STATUS[purchase.status]}</Badge></td>
              <td><div className="actions">
                {canDecidePurchase && purchase.status === "PENDING_APPROVAL" && purchase.created_by !== me.user_account_id && <>
                  <button type="button" onClick={() => void decidePurchase(purchase, "APPROVED")}>Approuver</button>
                  {rejectingPurchase === purchase.fuel_purchase_order_id ? <><select aria-label="Motif du refus de commande" value={purchaseRejectReason} onChange={(e) => setPurchaseRejectReason(e.target.value as keyof typeof PURCHASE_REJECT_REASONS)}><Options map={PURCHASE_REJECT_REASONS} /></select><button type="button" className="danger" onClick={() => void decidePurchase(purchase, "REJECTED", purchaseRejectReason)}>Confirmer</button><button type="button" onClick={() => setRejectingPurchase(null)}>Annuler</button></> : <button type="button" className="danger" onClick={() => setRejectingPurchase(purchase.fuel_purchase_order_id)}>Refuser</button>}
                </>}
                {canReceivePurchase && (purchase.status === "APPROVED" || purchase.status === "PARTIALLY_RECEIVED") && <button type="button" onClick={() => { setSelectedPurchaseId(purchase.fuel_purchase_order_id); setPanel("purchase-receipt"); }}>Réceptionner</button>}
              </div></td>
            </tr>)}</tbody>
          </table>
          <Pager page={purchasePage} pageSize={PAGE_SIZE} total={purchases.data?.total ?? 0} onPage={setPurchasePage} />
        </DataState>
      </div>}

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
        <div className="page-head"><div><h2>Consommation des véhicules</h2><p className="muted">Calculée entre deux pleins complets approuvés ; les ravitaillements intermédiaires sont additionnés.</p></div>
          <label>Véhicule<select value={vehicleId} onChange={(e) => { setVehicleId(e.target.value); setConsumptionPage(1); }}><option value="">Choisir un véhicule</option>{vehicles.data?.items.map((vehicle) => <option key={vehicle.vehicle_id} value={vehicle.vehicle_id}>{vehicle.fleet_number}</option>)}</select></label>
          <label>Compteur<select value={consumptionMeter} onChange={(e) => { setConsumptionMeter(e.target.value as "" | MeterKind); setConsumptionPage(1); }}><option value="">Tous</option><Options map={METER_KINDS} /></select></label>
        </div>
        {!vehicleId ? <p className="muted">Sélectionnez un véhicule pour consulter ses périodes de consommation.</p> : <>
          <DataState loading={consumption.isLoading} error={consumption.error} empty={(consumption.data?.items.length ?? 0) === 0} emptyText="Aucune période complète. Marquez les prochains pleins complets lors de la demande de ravitaillement.">
            <table><thead><tr><th>Période</th><th>Carburant</th><th>Distance / heures</th><th>Volume</th><th>Consommation</th><th>Référence</th><th>Analyse</th></tr></thead>
              <tbody>{consumption.data?.items.map((row: Consumption) => <tr key={row.fuel_issue_id}>
                <td>{formatDateTime(row.interval_start_at, timezoneOf(row.site_id))}<br />→ {formatDateTime(row.interval_end_at, timezoneOf(row.site_id))}</td>
                <td>{FUEL_TYPES[row.fuel_type]}</td><td>{number(row.meter_delta)} {row.meter_kind === "ODOMETER" ? "km" : "h"}</td><td>{liters(row.fuel_liters)}</td>
                <td>{number(row.rate_liters_per_unit)} {row.meter_kind === "ODOMETER" ? "L/100 km" : "L/h"}</td>
                <td>{row.comparison_median_rate === null ? "Historique insuffisant" : `${number(row.comparison_median_rate)} ${row.meter_kind === "ODOMETER" ? "L/100 km" : "L/h"} · ${row.comparison_interval_count} périodes`}</td>
                <td><Badge tone={row.is_anomaly ? "warn" : "ok"}>{row.is_anomaly ? "À examiner" : "Dans la référence"}</Badge></td>
              </tr>)}</tbody>
            </table><Pager page={consumptionPage} pageSize={PAGE_SIZE} total={consumption.data?.total ?? 0} onPage={setConsumptionPage} />
          </DataState>
          <p className="muted small">Un écart supérieur à 1,5× la médiane des périodes comparables précédentes (au moins 3) est signalé « à examiner ». C'est un indicateur de contrôle, pas une conclusion de fraude.</p>
        </>}
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

function SupplierForm({ siteId, onCancel, onDone }: { siteId: string | null; onCancel: () => void; onDone: () => void }) {
  const { sites } = useSites();
  const [site, setSite] = useState(siteId ?? sites[0]?.site_id ?? "");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  return <ActionForm title="Créer un fournisseur de carburant" submitLabel="Créer le fournisseur" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/suppliers", { body: { site_id: site, code: code.trim(), name: name.trim() } })}>
    <label>Site<select required value={site} onChange={(e) => setSite(e.target.value)}><option value="">Choisir un site</option>{sites.map((item) => <option key={item.site_id} value={item.site_id}>{item.code} — {item.name}</option>)}</select></label>
    <label>Code fournisseur<input required maxLength={32} pattern="[A-Za-z0-9_-]{1,32}" value={code} onChange={(e) => setCode(e.target.value)} /></label>
    <label>Raison sociale<input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
  </ActionForm>;
}

function PurchaseForm({ tanks, suppliers, timezoneOf, onCancel, onDone }: { tanks: Tank[]; suppliers: FuelSupplier[]; timezoneOf: (siteId: string | null | undefined) => string; onCancel: () => void; onDone: () => void }) {
  const [tankId, setTankId] = useState(tanks[0]?.fuel_tank_id ?? "");
  const tank = tanks.find((item) => item.fuel_tank_id === tankId);
  const availableSuppliers = suppliers.filter((item) => item.site_id === tank?.site_id);
  const [supplierId, setSupplierId] = useState("");
  const [reference, setReference] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [currency, setCurrency] = useState<Currency>("GNF");
  const [date, setDate] = useState(utcToZonedInput(new Date(), timezoneOf(tank?.site_id)));
  return <ActionForm title="Nouvelle commande de carburant" submitLabel="Soumettre la commande" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/purchases", { body: {
    fuel_supplier_id: supplierId,
    fuel_tank_id: tankId,
    reference: reference.trim(),
    quantity_liters: Number(quantity),
    unit_price: Number(unitPrice),
    currency,
    ordered_at: zonedInputToUtc(date, timezoneOf(tank?.site_id)).toISOString(),
  } })}>
    <label>Cuve destinataire<select required value={tankId} onChange={(e) => { setTankId(e.target.value); setSupplierId(""); }}>{tanks.map((item) => <option key={item.fuel_tank_id} value={item.fuel_tank_id}>{item.code} · {FUEL_TYPES[item.fuel_type]}</option>)}</select></label>
    <label>Fournisseur<select required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}><option value="">Choisir un fournisseur du site</option>{availableSuppliers.map((item) => <option key={item.fuel_supplier_id} value={item.fuel_supplier_id}>{item.code} — {item.name}</option>)}</select></label>
    <label>Référence de commande<input required maxLength={60} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
    <label>Quantité commandée (L)<input required type="number" min="0.001" max="2000000" step="0.001" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
    <label>Prix unitaire<input required type="number" min="0.01" step="0.01" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} /></label>
    <label>Devise<select value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}><Options map={CURRENCIES} /></select></label>
    <label>Date de commande<input required type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>
    <p className="muted small">Une autre personne devra approuver la commande avant toute réception.</p>
  </ActionForm>;
}

function PurchaseReceiptForm({ purchase, timezoneOf, onCancel, onDone }: { purchase: FuelPurchase | undefined; timezoneOf: (siteId: string | null | undefined) => string; onCancel: () => void; onDone: () => void }) {
  const [quantity, setQuantity] = useState("");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState(utcToZonedInput(new Date(), timezoneOf(purchase?.site_id)));
  if (!purchase) return null;
  return <ActionForm title={`Réception — commande ${purchase.reference}`} submitLabel="Enregistrer la réception" onCancel={onCancel} onDone={onDone} onSubmit={() => call("post", "/fuel/purchases/{fuel_purchase_order_id}/receipts", { path: { fuel_purchase_order_id: purchase.fuel_purchase_order_id }, body: {
    liters: Number(quantity),
    delivery_reference: reference.trim(),
    occurred_at: zonedInputToUtc(date, timezoneOf(purchase.site_id)).toISOString(),
  } })}>
    <p className="muted">Cuve {purchase.tank_code} · reste à livrer : {liters(purchase.remaining_liters)}.</p>
    <label>Quantité livrée (L)<input required type="number" min="0.001" max={Number(purchase.remaining_liters)} step="0.001" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></label>
    <label>Référence du bon de livraison<input required maxLength={60} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
    <label>Date de réception<input required type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} /></label>
  </ActionForm>;
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
  const [fullTank, setFullTank] = useState(false);
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
    full_tank: fullTank,
    requested_at: zonedInputToUtc(date, timezoneOf(selectedTank?.site_id)).toISOString(),
  } })}>
    <label>Cuve<select required value={tankId} onChange={(e) => setTankId(e.target.value)}>{tanks.map((tank) => <option key={tank.fuel_tank_id} value={tank.fuel_tank_id}>{tank.code} · {FUEL_TYPES[tank.fuel_type]} · {liters(tank.available_liters)} disponible</option>)}</select></label>
    <label>Véhicule et conducteur<select required value={assignmentId} onChange={(e) => setAssignmentId(e.target.value)}><option value="">Choisir une affectation active</option>{activeAssignments.map((item) => <option key={item.vehicle_assignment_id} value={item.vehicle_assignment_id}>{item.vehicle_fleet_number} — {item.driver_display_name}</option>)}</select></label>
    <DataState loading={assignments.isLoading} error={assignments.error} empty={activeAssignments.length === 0} emptyText="Aucune affectation active disponible sur ce site."><span className="muted small">Le serveur vérifiera à nouveau l'affectation au moment de l'enregistrement.</span></DataState>
    <label>Quantité demandée (L)<input required type="number" min="0.001" max="100000" step="0.001" value={litersValue} onChange={(e) => setLitersValue(e.target.value)} /></label>
    <label>Compteur (si disponible)<select value={meterKind} onChange={(e) => setMeterKind(e.target.value as "" | MeterKind)}><option value="">Non renseigné</option><Options map={METER_KINDS} /></select></label>
    {meterKind && <label>Valeur ({meterKind === "ODOMETER" ? "km" : "h"})<input required type="number" min="0" step="0.1" value={meterValue} onChange={(e) => setMeterValue(e.target.value)} /></label>}
    <label className="checkbox"><input type="checkbox" checked={fullTank} disabled={!meterKind || !meterValue} onChange={(e) => setFullTank(e.target.checked)} /> Plein complet (réservoir rempli)</label>
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

function number(value: string): string {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 }).format(Number(value));
}

function money(value: string, currency: Currency): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency, maximumFractionDigits: currency === "GNF" ? 0 : 2 }).format(Number(value));
}

function PumpCreateForm({ tanks, onCancel, onDone }: { tanks: Tank[]; onCancel: () => void; onDone: () => void }) {
  const [tankId, setTankId] = useState(tanks[0]?.fuel_tank_id ?? "");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  return <form className="card" aria-label="Création d'une pompe" onSubmit={(event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    void call("post", "/fuel/pumps", { body: { fuel_tank_id: tankId, code: code.trim(), name: name.trim() } })
      .then(() => onDone())
      .catch(setError)
      .finally(() => setSaving(false));
  }}>
    <h2>Nouvelle pompe à carburant</h2>
    {error !== null && <ErrorMessage error={error} />}
    <label>Cuve de rattachement<select required value={tankId} onChange={(event) => setTankId(event.target.value)}>
      {tanks.map((tank) => <option key={tank.fuel_tank_id} value={tank.fuel_tank_id}>{tank.code} · {FUEL_TYPES[tank.fuel_type]}</option>)}
    </select></label>
    <label>Code pompe<input required maxLength={32} pattern="[A-Za-z0-9_-]{1,32}" value={code} onChange={(event) => setCode(event.target.value)} /></label>
    <label>Nom pompe<input required minLength={2} maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>
    <div className="actions"><button type="submit" disabled={saving || !tankId}>{saving ? "Création…" : "Créer la pompe"}</button><button type="button" onClick={onCancel}>Annuler</button></div>
  </form>;
}
