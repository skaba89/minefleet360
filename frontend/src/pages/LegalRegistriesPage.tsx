import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, Pager } from "../components/common";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 25;
type Contract = Schemas["ContractOut"];
type Policy = Schemas["InsuranceOut"];

type LegalTab = "contracts" | "insurance";

export function authorizedLegalTab(tab: LegalTab, contracts: boolean, insurance: boolean): LegalTab {
  if (tab === "contracts" && !contracts && insurance) return "insurance";
  if (tab === "insurance" && !insurance && contracts) return "contracts";
  return tab;
}

export function LegalRegistriesPage() {
  const me = useMe();
  const { siteId } = useSites();
  const [tab, setTab] = useState<LegalTab>("contracts");
  const [page, setPage] = useState(1);
  const canReadContracts = can(me.grants, "legal.contract.read", siteId);
  const canReadPolicies = can(me.grants, "legal.insurance.read", siteId);
  const activeTab = authorizedLegalTab(tab, canReadContracts, canReadPolicies);
  const contracts = useQuery({
    queryKey: ["legal-contracts", siteId, page],
    enabled: activeTab === "contracts" && canReadContracts,
    queryFn: () => read("/legal-contracts", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  const policies = useQuery({
    queryKey: ["insurance-policies", siteId, page],
    enabled: activeTab === "insurance" && canReadPolicies,
    queryFn: () => read("/insurance-policies", { query: { site_id: siteId, page, page_size: PAGE_SIZE } }),
  });
  if (!canReadContracts && !canReadPolicies) {
    return <p className="error" role="alert">Vous n'avez pas accès aux registres juridiques.</p>;
  }
  const current = activeTab === "contracts" ? contracts : policies;
  const allowed = activeTab === "contracts" ? canReadContracts : canReadPolicies;
  return (
    <section>
      <h1>Contrats et assurances</h1>
      <p className="muted">Registres de consultation. Les signatures et les attestations doivent être vérifiées séparément.</p>
      <div role="group" aria-label="Choisir un registre">
        {canReadContracts && <button type="button" aria-pressed={activeTab === "contracts"} onClick={() => { setTab("contracts"); setPage(1); }}>Contrats</button>}
        {canReadPolicies && <button type="button" aria-pressed={activeTab === "insurance"} onClick={() => { setTab("insurance"); setPage(1); }}>Assurances</button>}
      </div>
      {!allowed ? <p className="error" role="alert">Accès non autorisé pour ce registre.</p> : (
        <DataState loading={current.isLoading} error={current.error} empty={!current.data?.items.length}>
          {activeTab === "contracts" ? (
            <table>
              <thead><tr><th>Référence</th><th>Intitulé</th><th>Type</th><th>Contrepartie</th><th>Statut</th></tr></thead>
              <tbody>{(contracts.data?.items ?? []).map((item: Contract) => (
                <tr key={item.contract_id}><td>{item.reference}</td><td>{item.title}</td><td>{item.contract_type}</td><td>{item.counterparty_name}</td><td>{item.status}</td></tr>
              ))}</tbody>
            </table>
          ) : (
            <table>
              <thead><tr><th>Police</th><th>Assureur</th><th>Garantie</th><th>Début</th><th>Fin</th></tr></thead>
              <tbody>{(policies.data?.items ?? []).map((item: Policy) => (
                <tr key={item.insurance_policy_id}><td>{item.policy_number}</td><td>{item.insurer_name}</td><td>{item.coverage_type}</td><td>{item.coverage_start}</td><td>{item.coverage_end}</td></tr>
              ))}</tbody>
            </table>
          )}
          <Pager page={page} pageSize={PAGE_SIZE} total={current.data?.total ?? 0} onPage={setPage} />
        </DataState>
      )}
    </section>
  );
}
