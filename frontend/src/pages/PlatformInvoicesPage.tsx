import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState, Pager } from "../components/common";
import { ActionForm } from "../components/forms";
import { can } from "../lib/permissions";

type Invoice = Schemas["InvoiceSummary"];
type InvoiceDetail = Schemas["InvoiceOut"];
type Tenant = Schemas["TenantSummary"];
type Subscription = Schemas["SubscriptionSummary"];
type InvoicePage = { items: Invoice[]; page: number; page_size: number; total: number };

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Brouillon",
  ISSUED: "Émise",
  VOIDED: "Annulée",
};

/** Libellés du cycle de vie d'abonnement (TRIAL/ACTIVE/… distinct du statut des factures). */
const SUBSCRIPTION_STATUS_LABEL: Record<string, string> = {
  TRIAL: "Essai",
  ACTIVE: "Actif",
  SUSPENDED: "Suspendu",
  CANCELLED: "Annulé",
  EXPIRED: "Essai expiré",
};

/** Format GNF : séparateur de milliers + suffixe (le franc guinéen n'a pas de subdivision). */
export function formatGnf(value: number): string {
  return `${value.toLocaleString("fr-FR")} GNF`;
}

function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("fr-FR") : "—";
}

function taxPercent(bp: number): string {
  return `${(bp / 100).toLocaleString("fr-FR")} %`;
}

/** Création d'une facture DRAFT : lignes saisies, ou préremplies depuis le tarif du plan. */
function CreateInvoiceForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [tenantId, setTenantId] = useState("");
  const [subscriptionId, setSubscriptionId] = useState("");
  const [taxBp, setTaxBp] = useState("0");
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");

  const tenants = useQuery({
    queryKey: ["saas-invoice-tenants"],
    queryFn: () => get<{ items: Tenant[] }>("/platform/tenants", { page: 1, page_size: 100 }),
  });
  const subscriptions = useQuery({
    queryKey: ["saas-invoice-subscriptions", tenantId],
    enabled: tenantId !== "",
    queryFn: () =>
      get<{ items: Subscription[] }>(`/platform/tenants/${tenantId}/subscriptions`, {
        page: 1,
        page_size: 100,
      }),
  });
  const liveSubscriptions = (subscriptions.data?.items ?? []).filter(
    (subscription) => subscription.status !== "CANCELLED",
  );

  return (
    <ActionForm
      title="Créer une facture (brouillon)"
      submitLabel="Créer la facture"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        const lines = description.trim() === ""
          ? []
          : [{ description: description.trim(), quantity: Number(quantity), unit_price_gnf: Number(unitPrice) }];
        await request(`/platform/tenants/${tenantId}/invoices`, {
          method: "POST",
          body: {
            subscription_id: subscriptionId === "" ? null : subscriptionId,
            tax_rate_bp: Number(taxBp),
            period_start: periodStart === "" ? null : periodStart,
            period_end: periodEnd === "" ? null : periodEnd,
            lines,
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-invoices", tenantId] });
      }}>
      <label>Société cliente
        <select required value={tenantId} onChange={(e) => { setTenantId(e.target.value); setSubscriptionId(""); }}>
          <option value="">— choisir —</option>
          {(tenants.data?.items ?? []).map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.code} — {tenant.display_name}
            </option>
          ))}
        </select>
      </label>
      <label>Abonnement (facultatif : préremplit la ligne depuis le tarif du plan)
        <select value={subscriptionId} onChange={(e) => setSubscriptionId(e.target.value)}>
          <option value="">— aucune (saisie libre) —</option>
          {liveSubscriptions.map((subscription) => (
            <option key={subscription.subscription_id} value={subscription.subscription_id}>
              {subscription.plan_code} — {SUBSCRIPTION_STATUS_LABEL[subscription.status] ?? subscription.status}
            </option>
          ))}
        </select>
      </label>
      <label>Taxe (points de base : 1800 = 18 %)
        <input type="number" min={0} max={10000} required value={taxBp}
          onChange={(e) => setTaxBp(e.target.value)} />
      </label>
      <label>Début de période facturée (facultatif)
        <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
      </label>
      <label>Fin de période facturée (facultatif)
        <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
      </label>
      <label>Ligne — désignation (laisser vide pour une facture d'abonnement tarifé)
        <input type="text" maxLength={200} value={description}
          onChange={(e) => setDescription(e.target.value)} />
      </label>
      {description.trim() !== "" && (
        <>
          <label>Quantité
            <input type="number" min={1} max={100000} required value={quantity}
              onChange={(e) => setQuantity(e.target.value)} />
          </label>
          <label>Prix unitaire (GNF)
            <input type="number" min={0} required value={unitPrice}
              onChange={(e) => setUnitPrice(e.target.value)} />
          </label>
        </>
      )}
    </ActionForm>
  );
}

/** Émission (DRAFT → ISSUED) ou annulation motivée (→ VOIDED terminal) avec If-Match. */
function InvoiceActionForm({
  tenantId,
  invoice,
  action,
  onDone,
}: {
  tenantId: string;
  invoice: Invoice;
  action: "issue" | "void";
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const titles = {
    issue: `Émettre la facture ${invoice.number} (figer le document)`,
    void: `Annuler la facture ${invoice.number} (définitif)`,
  } as const;

  return (
    <ActionForm
      title={titles[action]}
      submitLabel="Confirmer"
      onCancel={onDone}
      onDone={onDone}
      onSubmit={async () => {
        await request(`/platform/tenants/${tenantId}/invoices/${invoice.invoice_id}/${action}`, {
          method: "POST",
          body: action === "void" ? { reason: reason.trim() } : {},
          ifMatch: `"${invoice.row_version}"`,
        });
        await queryClient.invalidateQueries({ queryKey: ["saas-invoices", tenantId] });
        await queryClient.invalidateQueries({ queryKey: ["saas-invoice-detail", invoice.invoice_id] });
      }}>
      {action === "void" && (
        <label>Motif d'annulation obligatoire
          <textarea required minLength={3} maxLength={500} value={reason}
            onChange={(e) => setReason(e.target.value)} />
        </label>
      )}
      {action === "issue" && (
        <p className="muted">
          L'émission fige la facture : ses lignes et montants deviennent immuables. Aucun encaissement
          n'est déclenché : le règlement se gère hors application (aucun moyen de paiement intégré).
        </p>
      )}
    </ActionForm>
  );
}

/** Détail d'une facture : lignes immuables et montants GNF figés. */
function InvoiceDetail({ tenantId, invoiceId }: { tenantId: string; invoiceId: string }) {
  const detail = useQuery({
    queryKey: ["saas-invoice-detail", invoiceId],
    queryFn: () => get<InvoiceDetail>(`/platform/tenants/${tenantId}/invoices/${invoiceId}`),
    retry: false,
  });
  if (detail.isLoading || detail.error) return null;
  const data = detail.data;
  if (!data) return null;
  return (
    <table>
      <caption>Détail de la facture {data.number} — statut {STATUS_LABEL[data.status] ?? data.status}</caption>
      <thead>
        <tr>
          <th scope="col">Désignation</th>
          <th scope="col">Quantité</th>
          <th scope="col">Prix unitaire</th>
          <th scope="col">Montant</th>
        </tr>
      </thead>
      <tbody>
        {data.lines.map((line) => (
          <tr key={line.line_id}>
            <td>{line.description}</td>
            <td>{line.quantity}</td>
            <td>{formatGnf(line.unit_price_gnf)}</td>
            <td>{formatGnf(line.amount_gnf)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row" colSpan={3}>Sous-total</th>
          <td>{formatGnf(data.subtotal_gnf)}</td>
        </tr>
        <tr>
          <th scope="row" colSpan={3}>Taxe ({taxPercent(data.tax_rate_bp)})</th>
          <td>{formatGnf(data.tax_gnf)}</td>
        </tr>
        <tr>
          <th scope="row" colSpan={3}>Total</th>
          <td>{formatGnf(data.total_gnf)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

/** Facturation des sociétés — lot 3 commercialisation (document interne, sans encaissement). */
export function PlatformInvoicesPage() {
  const me = useMe();
  const authorized = can(me.grants, "billing.invoice.manage");
  const [tenantId, setTenantId] = useState("");
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<{ invoice: Invoice; action: "issue" | "void" } | null>(null);
  const [detailId, setDetailId] = useState("");

  const tenants = useQuery({
    queryKey: ["saas-invoice-tenants"],
    enabled: authorized,
    queryFn: () => get<{ items: Tenant[] }>("/platform/tenants", { page: 1, page_size: 100 }),
  });
  const invoices = useQuery({
    queryKey: ["saas-invoices", tenantId, page],
    enabled: authorized && tenantId !== "",
    queryFn: () => get<InvoicePage>(`/platform/tenants/${tenantId}/invoices`, { page, page_size: 20 }),
  });

  if (!authorized) {
    return <AccessDenied />;
  }
  const items = invoices.data?.items ?? [];
  return (
    <section>
      <h1>Facturation SaaS</h1>
      <p className="muted">
        Factures internes de traçabilité : brouillon, émission (document figé), annulation motivée définitive.
        Montants en francs guinéens, taxe paramétrable en points de base. Aucun moyen de paiement intégré :
        le règlement se gère hors application, conformément à la règle « pas d'intégration non approuvée ».
      </p>
      <p>
        <button type="button" className="primary" onClick={() => setShowCreate(true)}>
          Créer une facture
        </button>
      </p>
      {showCreate && <CreateInvoiceForm onDone={() => setShowCreate(false)} />}
      {selected && (
        <InvoiceActionForm
          tenantId={tenantId}
          invoice={selected.invoice}
          action={selected.action}
          onDone={() => setSelected(null)}
        />
      )}
      <label>Société
        <select value={tenantId} onChange={(e) => { setTenantId(e.target.value); setPage(1); setSelected(null); setDetailId(""); }}>
          <option value="">— choisir une société —</option>
          {(tenants.data?.items ?? []).map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.code} — {tenant.display_name}
            </option>
          ))}
        </select>
      </label>
      {tenantId !== "" && (
        <DataState
          loading={invoices.isLoading}
          error={invoices.error}
          empty={items.length === 0}
          emptyText="Aucune facture pour cette société.">
          <table>
            <thead>
              <tr>
                <th scope="col">Numéro</th>
                <th scope="col">Statut</th>
                <th scope="col">Période</th>
                <th scope="col">Total</th>
                <th scope="col">Actions</th>
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
                      : `${formatDate(invoice.period_start)} → ${formatDate(invoice.period_end)}`}
                  </td>
                  <td>{formatGnf(invoice.total_gnf)}</td>
                  <td>
                    {invoice.status === "DRAFT" && (
                      <button type="button" onClick={() => { setSelected({ invoice, action: "issue" }); setShowCreate(false); }}>
                        Émettre
                      </button>
                    )}
                    {invoice.status !== "VOIDED" && (
                      <button type="button" onClick={() => { setSelected({ invoice, action: "void" }); setShowCreate(false); }}>
                        Annuler
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={page} pageSize={20} total={invoices.data?.total ?? 0} onPage={setPage} />
          {detailId !== "" && <InvoiceDetail tenantId={tenantId} invoiceId={detailId} />}
        </DataState>
      )}
      <p className="muted">
        Chaque création, émission ou annulation est journalisée par le serveur dans la société cible.
        Le numéro de facture (MF-année-numéro) est attribué par la plateforme, séquentiel et unique.
      </p>
    </section>
  );
}
