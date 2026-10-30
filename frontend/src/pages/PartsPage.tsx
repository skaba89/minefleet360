import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { read } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, Pager } from "../components/common";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 25;

export function PartsPage() {
  const me = useMe();
  const { siteId } = useSites();
  const [tab, setTab] = useState<"stocks" | "movements" | "reservations">("stocks");
  const [page, setPage] = useState(1);
  const permitted = can(me.grants, "maintenance.parts.read", siteId);
  const balances = useQuery({
    queryKey: ["part-balances", siteId, page],
    enabled: permitted && tab === "stocks",
    queryFn: () => read("/part-balances", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  const movements = useQuery({
    queryKey: ["part-movements", siteId, page],
    enabled: permitted && tab === "movements",
    queryFn: () => read("/part-movements", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  const reservations = useQuery({
    queryKey: ["part-reservations", siteId, page],
    enabled: permitted && tab === "reservations",
    queryFn: () => read("/part-reservations", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  const current = tab === "stocks" ? balances : tab === "movements" ? movements : reservations;
  if (!permitted) return <p role="alert">Vous n'avez pas accès au magasin de pièces.</p>;

  return (
    <section>
      <div className="page-head"><h1>Magasin de pièces détachées</h1></div>
      <p className="muted">Consultez les stocks, les mouvements et les réservations de votre périmètre.</p>
      <div className="filters" role="group" aria-label="Vue du magasin">
        {([
          ["stocks", "Stocks"],
          ["movements", "Mouvements"],
          ["reservations", "Réservations"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={tab === value ? "primary" : ""}
            aria-pressed={tab === value}
            onClick={() => { setTab(value); setPage(1); }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "stocks" && (
        <DataState loading={balances.isLoading} error={balances.error} empty={!balances.data?.items.length}>
          <table>
            <thead><tr><th>Pièce</th><th>Magasin</th><th>Physique</th><th>Réservé</th><th>Disponible</th></tr></thead>
            <tbody>{balances.data?.items.map((item) => (
              <tr key={item.spare_part_balance_id}>
                <td>{item.spare_part_id}</td><td>{item.spare_part_store_id}</td>
                <td>{item.on_hand}</td><td>{item.reserved}</td>
                <td>{item.on_hand - item.reserved}</td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {tab === "movements" && (
        <DataState loading={movements.isLoading} error={movements.error} empty={!movements.data?.items.length}>
          <table>
            <thead><tr><th>Référence</th><th>Type</th><th>Pièce</th><th>Magasin</th><th>Quantité</th></tr></thead>
            <tbody>{movements.data?.items.map((item) => (
              <tr key={item.spare_part_movement_id}>
                <td>{item.reference}</td><td>{item.movement_type}</td>
                <td>{item.spare_part_id}</td><td>{item.spare_part_store_id}</td><td>{item.quantity}</td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {tab === "reservations" && (
        <DataState loading={reservations.isLoading} error={reservations.error} empty={!reservations.data?.items.length}>
          <table>
            <thead><tr><th>Référence</th><th>Ordre de travail</th><th>Pièce</th><th>Quantité</th><th>Statut</th></tr></thead>
            <tbody>{reservations.data?.items.map((item) => (
              <tr key={item.spare_part_reservation_id}>
                <td>{item.reference}</td><td>{item.work_order_id}</td>
                <td>{item.spare_part_id}</td><td>{item.quantity}</td><td>{item.status}</td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {current.data && (
        <Pager page={page} pageSize={PAGE_SIZE} total={current.data.total} onPage={setPage} />
      )}
    </section>
  );
}
