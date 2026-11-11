import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState, Pager } from "../components/common";
import { Fact } from "../components/forms";
import { can } from "../lib/permissions";
import { formatGnf } from "./PlatformInvoicesPage";

type Invoice = Schemas["InvoiceSummary"];
type InvoiceDetail = Schemas["InvoiceOut"];
type InvoicePage = { items: Invoice[]; page: number; page_size: number; total: number };

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "En préparation",
  ISSUED: "Émise",
  VOIDED: "Annulée",
};

/** Factures de la société : lecture seule — aucun encaissement dans l'application (lot 3). */
export function TenantInvoicesPage() {
  const me = useMe();
  const authorized = can(me.grants, "billing.invoice.read");
  const [page, setPage] = useState(1);
  const [detailId, setDetailId] = useState("");

  const invoices = useQuery({
    queryKey: ["own-invoices", page],
    enabled: authorized,
    queryFn: () => get<InvoicePage>("/tenant/invoices", { page, page_size: 20 }),
    retry: false,
  });
  const detail = useQuery({
    queryKey: ["own-invoice-detail", detailId],
    enabled: authorized && detailId !== "",
    queryFn: () => get<InvoiceDetail>(`/tenant/invoices/${detailId}`),
    retry: false,
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  const items = invoices.data?.items ?? [];
  const detailData = detail.data;
  return (
    <section>
      <h1>Factures</h1>
      <p className="muted">
        Factures de votre société émises par l'équipe MineFleet 360. Le règlement se gère avec l'équipe
        commerciale : aucun moyen de paiement n'est intégré à l'application.
      </p>
      <DataState
        loading={invoices.isLoading}
        error={invoices.error}
        empty={items.length === 0}
        emptyText="Aucune facture pour votre société.">
        <table>
          <thead>
            <tr>
              <th scope="col">Numéro</th>
              <th scope="col">Statut</th>
              <th scope="col">Période</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {items.map((invoice) => (
              <tr key={invoice.invoice_id}>
                <td>
                  <button type="button" onClick={() => setDetailId(invoice.invoice_id === detailId ? "" : invoice.invoice_id)}>
                    {invoice.number}
                  </button>
                </td>
                <td>{STATUS_LABEL[invoice.status] ?? invoice.status}</td>
                <td>
                  {invoice.period_start === null && invoice.period_end === null
                    ? "—"
                    : `${new Date(invoice.period_start as string).toLocaleDateString("fr-FR")} → ${new Date(invoice.period_end as string).toLocaleDateString("fr-FR")}`}
                </td>
                <td>{formatGnf(invoice.total_gnf)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={20} total={invoices.data?.total ?? 0} onPage={setPage} />
        {detailData && (
          <dl className="card">
            <Fact label="Numéro">{detailData.number}</Fact>
            <Fact label="Statut">{STATUS_LABEL[detailData.status] ?? detailData.status}</Fact>
            <Fact label="Sous-total">{formatGnf(detailData.subtotal_gnf)}</Fact>
            <Fact label="Taxe">{formatGnf(detailData.tax_gnf)} ({(detailData.tax_rate_bp / 100).toLocaleString("fr-FR")} %)</Fact>
            <Fact label="Total">{formatGnf(detailData.total_gnf)}</Fact>
            <Fact label="Lignes">{detailData.lines.length}</Fact>
          </dl>
        )}
      </DataState>
    </section>
  );
}
