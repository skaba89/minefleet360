import { useQuery } from "@tanstack/react-query";

import { read, type Schemas } from "../api/client";
import { Badge, DataState } from "../components/common";
import { ExportButton } from "../components/ExportButton";
import { downloadCsv, stamp, toCsv } from "../lib/csv";
import { useSites } from "../site/SiteContext";

type Revenue = Schemas["ContractRevenue"];
type Status = Revenue["status"];

const STATUS_LABEL: Record<Status, string> = {
  COMPLETE: "Complet",
  PARTIAL: "Partiel (minimum)",
  INSUFFICIENT: "Données insuffisantes",
};
const STATUS_TONE: Record<Status, "ok" | "warn" | "bad"> = { COMPLETE: "ok", PARTIAL: "warn", INSUFFICIENT: "bad" };

function amount(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(value))}${currency ? ` ${currency}` : ""}`;
}

/**
 * Revenus par contrat (tarif × quantité mesurée) et marge sur coût complet par site, sur la période choisie.
 * Aucun revenu n'est estimé : sans pesée valide ni tarif en vigueur, le statut le dit.
 */
export function ContractRevenueSection({ days }: { days: string }) {
  const { siteId, sites } = useSites();
  const report = useQuery({
    queryKey: ["finance-revenue", siteId, days],
    queryFn: () => {
      const to = new Date();
      const from = new Date(to.getTime() - Number(days) * 86_400_000);
      return read("/finance/revenue", { query: { site_id: siteId, from: from.toISOString(), to: to.toISOString() } });
    },
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const contracts = report.data?.contracts ?? [];
  const margins = report.data?.sites ?? [];
  return (
    <section aria-label="Revenus et marges">
      <div className="page-head">
        <h2>Revenus et marges</h2>
        <ExportButton
          run={async () => {
            const header = ["Contrat", "Site", "Revenu", "Devise", "Statut", "Tonnes mesurées", "Heures mesurées", "Km mesurés", "Missions terminées", "Manques"];
            const data = contracts.map((c) => [
              c.contract_reference,
              siteCode.get(c.site_id) ?? c.site_id,
              c.amount ?? "",
              c.currency ?? "",
              STATUS_LABEL[c.status],
              c.tonnes,
              c.hours ?? "",
              c.km ?? "",
              c.missions_completed,
              c.missing.join(" | "),
            ]);
            downloadCsv(`revenus-${stamp()}.csv`, toCsv(header, data));
            return { truncated: false };
          }}
        />
      </div>
      <DataState loading={report.isLoading} error={report.error} empty={margins.length === 0 && contracts.length === 0} emptyText="Aucun revenu ni coût sur la période.">
        <table aria-label="Marge par site">
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">Revenus</th>
              <th scope="col">Coût complet</th>
              <th scope="col">Marge</th>
            </tr>
          </thead>
          <tbody>
            {margins.map((s) => (
              <tr key={s.site_id}>
                <td>{siteCode.get(s.site_id) ?? "—"}</td>
                <td>
                  {amount(s.revenue, s.currency)}
                  <div className="small muted">{STATUS_LABEL[s.revenue_status]}</div>
                </td>
                <td>{amount(s.cost, s.currency)}</td>
                <td>
                  {s.margin != null && (
                    <Badge tone={Number(s.margin) >= 0 ? "ok" : "bad"}>
                      {amount(s.margin, s.currency)}
                      {s.margin_percent != null && ` (${s.margin_percent} %)`}
                    </Badge>
                  )}
                  {s.not_comparable_reason && <div className="small muted">{s.not_comparable_reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table aria-label="Revenus par contrat">
          <thead>
            <tr>
              <th scope="col">Contrat</th>
              <th scope="col">Revenu</th>
              <th scope="col">Quantités mesurées</th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={c.contract_id}>
                <td>
                  {c.contract_reference}
                  <div className="small muted">{siteCode.get(c.site_id) ?? ""}</div>
                </td>
                <td>
                  {amount(c.amount, c.currency)} <Badge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                  {c.missing.length > 0 && <div className="small muted">{c.missing.join(" ; ")}</div>}
                </td>
                <td>
                  {c.tonnes} t
                  {Number(c.hours ?? 0) > 0 && ` · ${c.hours} h moteur`}
                  {Number(c.km ?? 0) > 0 && ` · ${c.km} km`} · {c.missions_completed} mission(s) terminée(s)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      <p className="muted small">
        Revenu = tarif en vigueur × quantité mesurée (pesées valides, missions terminées, compteur relevé avant le départ
        et après la fin de mission, à 2 h près). Marge = revenus − coût complet des
        engins du site, sans conversion de devises ; les missions sans contrat ne sont pas valorisées.
      </p>
    </section>
  );
}
