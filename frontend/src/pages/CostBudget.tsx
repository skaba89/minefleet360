import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ExportButton } from "../components/ExportButton";
import { ActionForm, orNull } from "../components/forms";
import { downloadCsv, stamp, toCsv } from "../lib/csv";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

type Row = Schemas["VarianceRow"];
type ComponentCode = Row["component"];

const COMPONENT_LABEL: Record<ComponentCode, string> = {
  FUEL: "Carburant",
  PARTS: "Pièces",
  LABOUR: "Main-d'œuvre",
  TYRES: "Pneumatiques",
};
const ACTUAL_LABEL: Record<Row["actual_status"], string> = {
  COMPLETE: "Complet",
  ESTIMATED: "Estimé",
  PARTIAL: "Partiel (minimum)",
  INSUFFICIENT: "Données insuffisantes",
  FUTURE: "Mois à venir",
};

function amount(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(value))}${currency ? ` ${currency}` : ""}`;
}

/**
 * Budget prévisionnel et écarts (contrôle de gestion, tranche 1) : site × mois × composante, comparés au coût complet
 * réel. Aucun écart n'est calculé entre devises différentes ; le statut du réel est toujours affiché.
 */
export function CostBudgetSection() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const queryClient = useQueryClient();
  const [entering, setEntering] = useState(false);
  const report = useQuery({
    queryKey: ["cost-budget-variance", siteId],
    queryFn: () => read("/costs/budget-variance", { query: { site_id: siteId } }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const rows = (report.data?.rows ?? []).filter((r) => r.budget_amount != null || (r.actual_amount != null && r.actual_amount !== "0.00"));
  return (
    <section aria-label="Budget et écarts">
      <div className="page-head">
        <h2>Budget et écarts</h2>
        <div className="row">
          {can(me.grants, "cost.budget.manage") && !entering && (
            <button type="button" className="primary" onClick={() => setEntering(true)}>
              Saisir un budget
            </button>
          )}
          <ExportButton
            run={async () => {
              const header = ["Site", "Mois", "Composante", "Budget", "Devise budget", "Réel", "Devise réel", "Statut du réel", "Écart", "Écart %", "Motif"];
              const data = rows.map((r) => [
                siteCode.get(r.site_id) ?? r.site_id,
                r.month,
                COMPONENT_LABEL[r.component],
                r.budget_amount ?? "",
                r.budget_currency ?? "",
                r.actual_amount ?? "",
                r.actual_currency ?? "",
                ACTUAL_LABEL[r.actual_status],
                r.variance_amount ?? "",
                r.variance_percent ?? "",
                r.not_comparable_reason ?? "",
              ]);
              downloadCsv(`budget-ecarts-${stamp()}.csv`, toCsv(header, data));
              return { truncated: false };
            }}
          />
        </div>
      </div>
      {entering && (
        <BudgetForm
          onCancel={() => setEntering(false)}
          onDone={() => {
            setEntering(false);
            void queryClient.invalidateQueries({ queryKey: ["cost-budget-variance"] });
          }}
        />
      )}
      <DataState loading={report.isLoading} error={report.error} empty={rows.length === 0} emptyText="Aucun budget ni coût sur la période.">
        <table>
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">Mois</th>
              <th scope="col">Composante</th>
              <th scope="col">Budget</th>
              <th scope="col">Réel</th>
              <th scope="col">Écart</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.site_id}-${r.month}-${r.component}`}>
                <td>{siteCode.get(r.site_id) ?? "—"}</td>
                <td>{r.month}</td>
                <td>{COMPONENT_LABEL[r.component]}</td>
                <td>{amount(r.budget_amount, r.budget_currency)}</td>
                <td>
                  {amount(r.actual_amount, r.actual_currency)}
                  <div className="small muted">{ACTUAL_LABEL[r.actual_status]}</div>
                </td>
                <td>
                  {r.variance_amount == null ? (
                    <span className="small muted">{r.not_comparable_reason}</span>
                  ) : (
                    <Badge tone={Number(r.variance_amount) > 0 ? "bad" : "ok"}>
                      {Number(r.variance_amount) > 0 ? "+" : ""}
                      {amount(r.variance_amount, r.budget_currency)}
                      {r.variance_percent != null && ` (${Number(r.variance_percent) > 0 ? "+" : ""}${r.variance_percent} %)`}
                    </Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      <p className="muted small">
        Réel = coût complet calculé (carburant estimé, pièces, main-d'œuvre valorisée, pneumatiques). Un écart positif est un
        dépassement. Aucune conversion entre devises ; la version de budget la plus récente fait foi (toutes sont journalisées).
      </p>
    </section>
  );
}

function BudgetForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const me = useMe();
  const { siteId, sites } = useSites();
  const allowed = sites.filter((s) => can(me.grants, "cost.budget.manage", s.site_id));
  const [form, setForm] = useState({
    site_id: siteId ?? allowed[0]?.site_id ?? "",
    month: new Date().toISOString().slice(0, 7),
    component: "FUEL" as ComponentCode,
    amount: "",
    currency: "GNF",
    note: "",
  });
  return (
    <ActionForm
      title="Saisir un budget"
      submitLabel="Enregistrer le budget"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/costs/budgets", {
          body: {
            site_id: form.site_id,
            month: form.month,
            component: form.component,
            amount: form.amount,
            currency: form.currency.trim().toUpperCase(),
            note: orNull(form.note),
          },
        })
      }
    >
      <label>
        Site
        <select required value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
          <option value="">— Choisir —</option>
          {allowed.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Mois
        <input type="month" required value={form.month} onChange={(e) => setForm({ ...form, month: e.target.value })} />
      </label>
      <label>
        Composante
        <select value={form.component} onChange={(e) => setForm({ ...form, component: e.target.value as ComponentCode })}>
          {(Object.keys(COMPONENT_LABEL) as ComponentCode[]).map((c) => (
            <option key={c} value={c}>
              {COMPONENT_LABEL[c]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Montant
        <input type="number" required min={0} step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
      </label>
      <label>
        Devise (ISO)
        <input required pattern="[A-Za-z]{3}" maxLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
      </label>
      <label>
        Commentaire (facultatif)
        <input maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </label>
      <p className="muted small">Une nouvelle saisie crée une nouvelle version ; les précédentes restent consultables dans le journal.</p>
    </ActionForm>
  );
}
