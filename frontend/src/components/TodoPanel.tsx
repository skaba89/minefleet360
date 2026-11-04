import { useQueries } from "@tanstack/react-query";
import { Link } from "react-router";

import { read } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { can, type Permission } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

interface Item {
  key: string;
  permission: Permission;
  label: (n: number) => string;
  to: string;
  tone: "bad" | "warn";
  count: (siteId: string | null) => Promise<number>;
}

const total = (page: { total: number }) => page.total;

/**
 * Éléments à traiter du périmètre de l'utilisateur, calculés à partir des API existantes : chaque ligne n'est
 * interrogée que si l'utilisateur a déjà le droit de lire la donnée correspondante. Aucune notification externe.
 */
const ITEMS: Item[] = [
  {
    key: "hse-mine",
    permission: "hse.incident.read",
    label: (n) => `${n} action(s) corrective(s) HSE à réaliser par vous`,
    to: "/hse",
    tone: "warn",
    count: () => read("/hse/corrective-actions", { query: { mine: true, status: "OPEN", page_size: 1 } }).then(total),
  },
  {
    key: "hse-overdue",
    permission: "hse.incident.read",
    label: (n) => `${n} action(s) corrective(s) HSE en retard`,
    to: "/hse",
    tone: "bad",
    count: (siteId) => read("/hse/summary", { query: { site_id: siteId } }).then((s) => s.overdue_actions),
  },
  {
    key: "hse-critical",
    permission: "hse.incident.read",
    label: (n) => `${n} incident(s) critique(s) non clôturé(s)`,
    to: "/hse",
    tone: "bad",
    count: (siteId) =>
      read("/hse/incidents", { query: { site_id: siteId, severity: "CRITICAL", open_only: true, page_size: 1 } }).then(total),
  },
  {
    key: "wo-requested",
    permission: "maintenance.work_order.manage",
    label: (n) => `${n} demande(s) d'intervention à valider`,
    to: "/atelier",
    tone: "warn",
    count: (siteId) => read("/work-orders", { query: { site_id: siteId, status: "REQUESTED", page_size: 1 } }).then(total),
  },
  {
    key: "wo-quality",
    permission: "maintenance.work_order.manage",
    label: (n) => `${n} intervention(s) en attente de contrôle qualité`,
    to: "/atelier",
    tone: "warn",
    count: (siteId) => read("/work-orders", { query: { site_id: siteId, status: "QUALITY_CHECK", page_size: 1 } }).then(total),
  },
  {
    key: "tyres",
    permission: "maintenance.tyre.read",
    label: (n) => `${n} pneu(s) en alerte (usure, pression ou contrôle en retard)`,
    to: "/pneus",
    tone: "warn",
    count: (siteId) => read("/tyres", { query: { site_id: siteId, alert_only: true, page_size: 1 } }).then(total),
  },
  {
    key: "gps-alerts",
    permission: "fleet.gps_alert.read",
    label: (n) => `${n} alerte(s) GPS à prendre en compte (vitesse, zones)`,
    to: "/flotte-gps/alertes",
    tone: "bad",
    count: (siteId) => read("/gps/alerts", { query: { site_id: siteId, unacknowledged: true, page_size: 1 } }).then(total),
  },
  {
    key: "fuel",
    permission: "fuel.stock.read",
    label: (n) => `${n} alerte(s) de stock carburant active(s)`,
    to: "/carburant",
    tone: "bad",
    count: (siteId) => read("/fuel/alerts", { query: { site_id: siteId, active_only: true, page: 1, page_size: 1 } }).then(total),
  },
];

export function TodoPanel() {
  const me = useMe();
  const { siteId } = useSites();
  const visible = ITEMS.filter((item) => can(me.grants, item.permission, siteId));
  const results = useQueries({
    queries: visible.map((item) => ({
      queryKey: ["todo", item.key, siteId],
      queryFn: () => item.count(siteId),
      refetchInterval: 60_000,
    })),
  });
  if (visible.length === 0) return null;
  const pending = visible
    .map((item, index) => ({ item, count: results[index]?.data }))
    .filter((entry): entry is { item: Item; count: number } => typeof entry.count === "number" && entry.count > 0);
  const loading = results.some((r) => r.isLoading);
  const failed = results.some((r) => r.isError);
  return (
    <section className="card" aria-label="À traiter">
      <h2>À traiter</h2>
      {loading && pending.length === 0 ? (
        <p className="muted" role="status">
          Chargement…
        </p>
      ) : pending.length === 0 ? (
        <p className="muted">Rien en attente dans votre périmètre.</p>
      ) : (
        <ul>
          {pending.map(({ item, count }) => (
            <li key={item.key}>
              <Link to={item.to} className={item.tone === "bad" ? "error-text" : "warn-text"}>
                {item.label(count)}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {failed && <p className="muted small">Certains indicateurs n'ont pas pu être chargés.</p>}
    </section>
  );
}
