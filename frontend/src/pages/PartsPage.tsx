import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { call, read } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage, Pager } from "../components/common";
import { can } from "../lib/permissions";
import { replenishmentCsv } from "../lib/replenishmentCsv";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 25;

export function PartsPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [action, setAction] = useState<"receipt" | "issue">("receipt");
  const [partId, setPartId] = useState("");
  const [storeId, setStoreId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [message, setMessage] = useState("");
  const [reservationOrderId, setReservationOrderId] = useState("");
  const [reservationPartId, setReservationPartId] = useState("");
  const [reservationStoreId, setReservationStoreId] = useState("");
  const [reservationQuantity, setReservationQuantity] = useState("1");
  const [reservationReference, setReservationReference] = useState("");
  const [reservationBusy, setReservationBusy] = useState(false);
  const [replenishmentPartId, setReplenishmentPartId] = useState("");
  const [replenishmentStoreId, setReplenishmentStoreId] = useState("");
  const [replenishmentQuantity, setReplenishmentQuantity] = useState("1");
  const [replenishmentReference, setReplenishmentReference] = useState("");
  const [replenishmentBusy, setReplenishmentBusy] = useState(false);
  const [decisionNote, setDecisionNote] = useState("");
  const [actingReplenishmentId, setActingReplenishmentId] = useState<string | null>(null);
  const [replenishmentError, setReplenishmentError] = useState<unknown>(null);
  const [reservationError, setReservationError] = useState<unknown>(null);
  const { siteId } = useSites();
  const canManageParts = can(me.grants, "maintenance.parts.manage", siteId);
  const canReceive = can(me.grants, "maintenance.parts.receive", siteId);
  const canIssue = can(me.grants, "maintenance.parts.issue", siteId);
  const canReserve = can(me.grants, "maintenance.parts.reserve", siteId);
  const canRelease = can(me.grants, "maintenance.parts.release", siteId);
  const canConsume = can(me.grants, "maintenance.parts.consume", siteId);
  const activeAction = canReceive && (action === "receipt" || !canIssue) ? "receipt" : "issue";
  const [tab, setTab] = useState<"stocks" | "movements" | "reservations" | "replenishments">("stocks");
  const [page, setPage] = useState(1);
  const [criticalOnly, setCriticalOnly] = useState(false);
  const permitted = can(me.grants, "maintenance.parts.read", siteId);
  const parts = useQuery({
    queryKey: ["parts-catalogue-labels"],
    enabled: permitted,
    queryFn: () => read("/parts", { query: { page: 1, page_size: 200 } }),
  });
  const stores = useQuery({
    queryKey: ["part-store-labels", siteId],
    enabled: permitted,
    queryFn: () => read("/part-stores", { query: { site_id: siteId, page: 1, page_size: 200 } }),
  });
  const partLabels = new Map(
    (parts.data?.items ?? []).map((part) => [part.spare_part_id, `${part.code} — ${part.name}`]),
  );
  const storeLabels = new Map(
    (stores.data?.items ?? []).map((store) => [store.spare_part_store_id, `${store.code} — ${store.name}`]),
  );
  const partLabel = (id: string) => partLabels.get(id) ?? id;
  const storeLabel = (id: string) => storeLabels.get(id) ?? id;

  const balances = useQuery({
    queryKey: ["part-balances", siteId, page, criticalOnly],
    enabled: permitted && tab === "stocks",
    queryFn: () => read("/part-balances", { query: { site_id: siteId, page, page_size: PAGE_SIZE, critical_only: criticalOnly } }),
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
  const replenishments = useQuery({
    queryKey: ["part-replenishments", siteId, page],
    enabled: permitted && tab === "replenishments",
    queryFn: () => read("/part-replenishments", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  const current = tab === "stocks" ? balances : tab === "movements" ? movements :
    tab === "reservations" ? reservations : replenishments;
  if (!permitted) return <p role="alert">Vous n'avez pas accès au magasin de pièces.</p>;

  return (
    <section>
      <div className="page-head"><h1>Magasin de pièces détachées</h1></div>
      <p className="muted">Consultez les stocks, les mouvements et les réservations de votre périmètre.</p>
      {(can(me.grants, "maintenance.parts.receive", siteId) ||
        can(me.grants, "maintenance.parts.issue", siteId)) && (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (saving) return;
            setSaving(true);
            setSaveError(null);
            setMessage("");
            try {
              const body = {
                spare_part_id: partId,
                spare_part_store_id: storeId,
                quantity: Number(quantity),
                reference: reference.trim(),
              };
              if (activeAction === "receipt") {
                await call("post", "/part-movements/receipts", { body });
              } else {
                await call("post", "/part-movements/issues", { body });
              }
              setMessage("Mouvement enregistré.");
              setReference("");
              await queryClient.invalidateQueries({ queryKey: ["part-balances"] });
              await queryClient.invalidateQueries({ queryKey: ["part-movements"] });
            } catch (error) {
              setSaveError(error);
            } finally {
              setSaving(false);
            }
          }}
        >
          <h2>Enregistrer un mouvement</h2>
          <div className="filters">
            <label>
              Opération
              <select value={activeAction} onChange={(event) => setAction(event.target.value as "receipt" | "issue")}>
                {can(me.grants, "maintenance.parts.receive", siteId) && <option value="receipt">Réception</option>}
                {can(me.grants, "maintenance.parts.issue", siteId) && <option value="issue">Sortie</option>}
              </select>
            </label>
            <label>
              Pièce
              <select required value={partId} onChange={(event) => setPartId(event.target.value)}>
                <option value="">Choisir une pièce</option>
                {parts.data?.items.map((part) => (
                  <option key={part.spare_part_id} value={part.spare_part_id}>{part.code} — {part.name}</option>
                ))}
              </select>
            </label>
            <label>
              Magasin
              <select required value={storeId} onChange={(event) => setStoreId(event.target.value)}>
                <option value="">Choisir un magasin</option>
                {stores.data?.items.map((store) => (
                  <option key={store.spare_part_store_id} value={store.spare_part_store_id}>
                    {store.code} — {store.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Quantité
              <input required type="number" min="0.001" step="0.001" value={quantity}
                onChange={(event) => setQuantity(event.target.value)} />
            </label>
            <label>
              Référence unique
              <input required maxLength={120} value={reference}
                onChange={(event) => setReference(event.target.value)} />
            </label>
          </div>
          <button
            className="primary"
            type="submit"
            disabled={saving || !partId || !storeId || !reference.trim() ||
              Number(quantity) <= 0 ||
              !(activeAction === "receipt" ? canReceive : canIssue)}
          >
            {saving ? "Enregistrement…" : "Valider le mouvement"}
          </button>
          {saveError !== null && <ErrorMessage error={saveError} />}
          {message && <p role="status">{message}</p>}
        </form>
      )}
      {canReserve && (
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (reservationBusy) return;
          setReservationBusy(true);
          setReservationError(null);
          setMessage("");
          try {
            await call("post", "/part-reservations", { body: {
              work_order_id: reservationOrderId.trim(),
              spare_part_id: reservationPartId,
              spare_part_store_id: reservationStoreId,
              quantity: Number(reservationQuantity),
              reference: reservationReference.trim(),
            } });
            setReservationReference("");
            setMessage("Réservation enregistrée.");
            await queryClient.invalidateQueries({ queryKey: ["part-reservations"] });
            await queryClient.invalidateQueries({ queryKey: ["part-balances"] });
          } catch (error) {
            setReservationError(error);
          } finally {
            setReservationBusy(false);
          }
        }}>
          <h2>Réserver des pièces pour un ordre de travail</h2>
          <div className="filters">
            <label>Identifiant de l'ordre de travail
              <input required value={reservationOrderId}
                onChange={(event) => setReservationOrderId(event.target.value)} />
            </label>
            <label>Pièce
              <select required value={reservationPartId}
                onChange={(event) => setReservationPartId(event.target.value)}>
                <option value="">Choisir une pièce</option>
                {parts.data?.items.map((part) => (
                  <option key={part.spare_part_id} value={part.spare_part_id}>{part.code} — {part.name}</option>
                ))}
              </select>
            </label>
            <label>Magasin
              <select required value={reservationStoreId}
                onChange={(event) => setReservationStoreId(event.target.value)}>
                <option value="">Choisir un magasin</option>
                {stores.data?.items.map((store) => (
                  <option key={store.spare_part_store_id} value={store.spare_part_store_id}>
                    {store.code} — {store.name}
                  </option>
                ))}
              </select>
            </label>
            <label>Quantité
              <input required type="number" min="0.001" step="0.001" value={reservationQuantity}
                onChange={(event) => setReservationQuantity(event.target.value)} />
            </label>
            <label>Référence unique
              <input required maxLength={120} value={reservationReference}
                onChange={(event) => setReservationReference(event.target.value)} />
            </label>
          </div>
          <button className="primary" type="submit" disabled={reservationBusy || !reservationOrderId.trim() ||
            !reservationPartId || !reservationStoreId || !reservationReference.trim() ||
            Number(reservationQuantity) <= 0}>
            {reservationBusy ? "Réservation…" : "Réserver"}
          </button>
      {reservationError !== null && <ErrorMessage error={reservationError} />}
        </form>
      )}
      <div className="filters" role="group" aria-label="Vue du magasin">
        {([
          ["stocks", "Stocks"],
          ["movements", "Mouvements"],
          ["reservations", "Réservations"],
          ["replenishments", "Réapprovisionnements"],
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
        <label className="checkbox">
          <input type="checkbox" checked={criticalOnly} onChange={(event) => { setCriticalOnly(event.target.checked); setPage(1); }} />
          Afficher tous les stocks critiques
        </label>
      )}
      {tab === "stocks" && (
        <div>
          <button type="button" disabled={!balances.data?.items.length}
            onClick={() => {
              const rows = (balances.data?.items ?? []).map((item) => ({
                part: partLabel(item.spare_part_id),
                store: storeLabel(item.spare_part_store_id),
                available: item.on_hand - item.reserved,
                threshold: item.low_stock_threshold,
              }));
              const blob = new Blob([replenishmentCsv(rows)], { type: "text/csv;charset=utf-8" });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = "minefleet-reapprovisionnement-brouillon.csv";
              link.click();
              URL.revokeObjectURL(url);
            }}>
            Exporter un brouillon de réapprovisionnement (page affichée)
          </button>
          <p className="muted small">Export local de la page courante uniquement, sans commande d'achat.</p>
        </div>
      )}
      {tab === "stocks" && (
        <DataState loading={balances.isLoading} error={balances.error} empty={!balances.data?.items.length}>
          <table>
            <thead><tr><th>Pièce</th><th>Magasin</th><th>Physique</th><th>Réservé</th><th>Disponible</th><th>Seuil</th><th>Manquant au seuil</th><th>Alerte</th></tr></thead>
            <tbody>{balances.data?.items.map((item) => (
              <tr key={item.spare_part_balance_id}>
                <td>{partLabel(item.spare_part_id)}</td><td>{storeLabel(item.spare_part_store_id)}</td>
                <td>{item.on_hand}</td><td>{item.reserved}</td>
                <td>{item.on_hand - item.reserved}</td>
                <td>{item.low_stock_threshold}</td>
                <td>{Math.max(0, item.low_stock_threshold - (item.on_hand - item.reserved))}</td>
                <td>{item.on_hand - item.reserved <= item.low_stock_threshold ?
                  <strong className="warn-text">Stock faible</strong> : "Stock suffisant"}</td>
              </tr>
            ))}</tbody>
          </table>
          <p className="muted small">Quantité manquante indicative pour atteindre le seuil ; à valider avant tout achat.</p>
          {criticalOnly && balances.data && !balances.data.items.some((item) =>
            item.on_hand - item.reserved <= item.low_stock_threshold) && (
            <p role="status">Aucun stock critique pour cette recherche.</p>
          )}
        </DataState>
      )}
      {tab === "movements" && (
        <DataState loading={movements.isLoading} error={movements.error} empty={!movements.data?.items.length}>
          <table>
            <thead><tr><th>Référence</th><th>Type</th><th>Pièce</th><th>Magasin</th><th>Quantité</th></tr></thead>
            <tbody>{movements.data?.items.map((item) => (
              <tr key={item.spare_part_movement_id}>
                <td>{item.reference}</td><td>{item.movement_type}</td>
                <td>{partLabel(item.spare_part_id)}</td><td>{storeLabel(item.spare_part_store_id)}</td><td>{item.quantity}</td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {tab === "reservations" && (
        <DataState loading={reservations.isLoading} error={reservations.error} empty={!reservations.data?.items.length}>
          <table>
            <thead><tr><th>Référence</th><th>Ordre de travail</th><th>Pièce</th><th>Quantité</th><th>Statut</th><th>Actions</th></tr></thead>
            <tbody>{reservations.data?.items.map((item) => (
              <tr key={item.spare_part_reservation_id}>
                <td>{item.reference}</td><td><Link to={`/atelier/${item.work_order_id}`}>Voir l’OT</Link></td>
                <td>{partLabel(item.spare_part_id)}</td><td>{item.quantity}</td>
                <td>
                  {item.status}
                  {item.status === "ACTIVE" && (canRelease || canConsume) && (
                    <div className="filters">
                      {(["release", "consume"] as const).filter((operation) =>
                        operation === "release" ? canRelease : canConsume).map((operation) => (
                        <button key={operation} type="button" disabled={reservationBusy}
                          onClick={async () => {
                            if (reservationBusy) return;
                            setReservationBusy(true);
                            setReservationError(null);
                            setMessage("");
                            try {
                              if (operation === "release") {
                                await call("post", "/part-reservations/{reservation_id}/release", {
                                  path: { reservation_id: item.spare_part_reservation_id },
                                });
                              } else {
                                await call("post", "/part-reservations/{reservation_id}/consume", {
                                  path: { reservation_id: item.spare_part_reservation_id },
                                });
                              }
                              setMessage(operation === "release" ? "Réservation libérée." : "Pièces consommées.");
                              await queryClient.invalidateQueries({ queryKey: ["part-reservations"] });
                              await queryClient.invalidateQueries({ queryKey: ["part-balances"] });
                              await queryClient.invalidateQueries({ queryKey: ["part-movements"] });
                            } catch (error) {
                              setReservationError(error);
                            } finally {
                              setReservationBusy(false);
                            }
                          }}>
                          {operation === "release" ? "Libérer" : "Consommer"}
                        </button>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {tab === "replenishments" && canManageParts && (
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (replenishmentBusy) return;
          setReplenishmentBusy(true);
          setReplenishmentError(null);
          setMessage("");
          try {
            await call("post", "/part-replenishments", { body: {
              spare_part_id: replenishmentPartId,
              spare_part_store_id: replenishmentStoreId,
              quantity: Number(replenishmentQuantity),
              reference: replenishmentReference.trim(),
            } });
            setReplenishmentReference("");
            setMessage("Brouillon de réapprovisionnement créé.");
            setPage(1);
            await queryClient.invalidateQueries({ queryKey: ["part-replenishments"] });
          } catch (error) {
            setReplenishmentError(error);
          } finally {
            setReplenishmentBusy(false);
          }
        }}>
          <h2>Créer une demande de réapprovisionnement</h2>
          <div className="filters">
            <label>Pièce
              <select required value={replenishmentPartId}
                onChange={(event) => setReplenishmentPartId(event.target.value)}>
                <option value="">Choisir une pièce</option>
                {parts.data?.items.map((part) => (
                  <option key={part.spare_part_id} value={part.spare_part_id}>
                    {part.code} — {part.name}
                  </option>
                ))}
              </select>
            </label>
            <label>Magasin
              <select required value={replenishmentStoreId}
                onChange={(event) => setReplenishmentStoreId(event.target.value)}>
                <option value="">Choisir un magasin</option>
                {stores.data?.items.map((store) => (
                  <option key={store.spare_part_store_id} value={store.spare_part_store_id}>
                    {store.code} — {store.name}
                  </option>
                ))}
              </select>
            </label>
            <label>Quantité
              <input type="number" required min="0.001" step="0.001"
                value={replenishmentQuantity}
                onChange={(event) => setReplenishmentQuantity(event.target.value)} />
            </label>
            <label>Référence unique
              <input required maxLength={120} value={replenishmentReference}
                onChange={(event) => setReplenishmentReference(event.target.value)} />
            </label>
          </div>
          <button className="primary" type="submit"
            disabled={replenishmentBusy || !replenishmentPartId || !replenishmentStoreId ||
              !replenishmentReference.trim() || !(Number(replenishmentQuantity) > 0)}>
            {replenishmentBusy ? "Création…" : "Créer le brouillon"}
          </button>
          {replenishmentError !== null && <ErrorMessage error={replenishmentError} />}
        </form>
      )}
      {tab === "replenishments" && canManageParts && (
        <label>Justification de la décision (obligatoire)
          <input value={decisionNote} maxLength={500}
            onChange={(event) => setDecisionNote(event.target.value)} />
        </label>
      )}
      {tab === "replenishments" && (
        <DataState loading={replenishments.isLoading} error={replenishments.error}
          empty={!replenishments.data?.items.length}>
          <table>
            <thead><tr><th>Référence</th><th>Pièce</th><th>Magasin</th><th>Quantité</th><th>Statut</th></tr></thead>
            <tbody>{replenishments.data?.items.map((item) => (
              <tr key={item.replenishment_id}>
                <td>{item.reference}</td>
                <td>{partLabel(item.spare_part_id)}</td>
                <td>{storeLabel(item.spare_part_store_id)}</td>
                <td>{item.quantity}</td>
                <td>{({
                  DRAFT: "Brouillon", SUBMITTED: "Soumis",
                  APPROVED: "Approuvé", REJECTED: "Rejeté",
                } as Record<string, string>)[item.status] ?? item.status}</td>
                <td>
                  <span>Demandeur : {item.created_by}</span>
                  {item.submitted_at && <div>Soumise : {new Date(item.submitted_at).toLocaleString("fr-FR")}</div>}
                  {item.decision_by && <div>Décideur : {item.decision_by}</div>}
                  {item.decided_at && <div>Décision : {new Date(item.decided_at).toLocaleString("fr-FR")}</div>}
                  {item.decision_note && <div>Motif : {item.decision_note}</div>}
                </td>
                <td>
                  {canManageParts && item.status === "DRAFT" && (
                    <button type="button" disabled={actingReplenishmentId !== null}
                      onClick={async () => {
                        setActingReplenishmentId(item.replenishment_id);
                        setReplenishmentError(null);
                        try {
                          await call("post", "/part-replenishments/{replenishment_id}/submit", {
                            path: { replenishment_id: item.replenishment_id },
                          });
                          setMessage("Demande soumise.");
                          await queryClient.invalidateQueries({ queryKey: ["part-replenishments"] });
                        } catch (error) {
                          setReplenishmentError(error);
                        } finally {
                          setActingReplenishmentId(null);
                        }
                      }}>Soumettre</button>
                  )}
                  {canManageParts && item.status === "SUBMITTED" && (
                    <div className="filters">
                      {(["APPROVE", "REJECT"] as const).map((decision) => (
                        <button key={decision} type="button"
                          disabled={actingReplenishmentId !== null || !decisionNote.trim()}
                          onClick={async () => {
                            setActingReplenishmentId(item.replenishment_id);
                            setReplenishmentError(null);
                            try {
                              await call("post", "/part-replenishments/{replenishment_id}/decision", {
                                path: { replenishment_id: item.replenishment_id },
                                body: { action: decision, note: decisionNote.trim() },
                              });
                              setDecisionNote("");
                              setMessage(decision === "APPROVE" ? "Demande approuvée." : "Demande rejetée.");
                              await queryClient.invalidateQueries({ queryKey: ["part-replenishments"] });
                            } catch (error) {
                              setReplenishmentError(error);
                            } finally {
                              setActingReplenishmentId(null);
                            }
                          }}>{decision === "APPROVE" ? "Approuver" : "Rejeter"}</button>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </DataState>
      )}
      {replenishmentError !== null && <ErrorMessage error={replenishmentError} />}
      {reservationError !== null && <ErrorMessage error={reservationError} />}
      {message && <p role="status">{message}</p>}
      {current.data && (
        <Pager page={page} pageSize={PAGE_SIZE} total={current.data.total} onPage={setPage} />
      )}
    </section>
  );
}
