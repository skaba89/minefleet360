import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage, Pager } from "../components/common";
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
  const queryClient = useQueryClient();
  const [reference, setReference] = useState("");
  const [title, setTitle] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [contractType, setContractType] = useState<Schemas["ContractDraftInput"]["contract_type"]>("SUPPLIER");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const { siteId } = useSites();
  const [tab, setTab] = useState<LegalTab>("contracts");
  const [page, setPage] = useState(1);
  const canReadContracts = can(me.grants, "legal.contract.read", siteId);
  const canCreateContract = Boolean(siteId) && can(me.grants, "legal.contract.create", siteId);
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
      {activeTab === "contracts" && canCreateContract && siteId && (
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (saving) return;
          setSaving(true);
          setSaveError(null);
          setNotice("");
          try {
            await call("post", "/legal-contracts", {
              body: {
                site_id: siteId,
                reference: reference.trim(),
                title: title.trim(),
                counterparty_name: counterparty.trim(),
                contract_type: contractType,
              },
            });
            setReference("");
            setTitle("");
            setCounterparty("");
            setPage(1);
            await queryClient.invalidateQueries({ queryKey: ["legal-contracts"] });
            setNotice("Contrat enregistré comme brouillon. Aucune signature n'a été effectuée.");
          } catch (error) {
            setSaveError(error);
          } finally {
            setSaving(false);
          }
        }}>
          <h2>Nouveau contrat — brouillon</h2>
          <label>Référence <input required maxLength={120} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
          <label>Intitulé <input required maxLength={240} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label>Contrepartie <input required maxLength={240} value={counterparty} onChange={(e) => setCounterparty(e.target.value)} /></label>
          <label>Type de contrat
            <select value={contractType} onChange={(e) => setContractType(e.target.value as Schemas["ContractDraftInput"]["contract_type"])}>
              <option value="SUPPLIER">Fournisseur</option>
              <option value="TRANSPORT">Transport</option>
              <option value="SUBCONTRACTOR">Sous-traitance</option>
              <option value="EMPLOYMENT">Emploi</option>
              <option value="LEASE">Location</option>
              <option value="OTHER">Autre</option>
            </select>
          </label>
          <button type="submit" disabled={saving || !reference.trim() || !title.trim() || !counterparty.trim()}>
            {saving ? "Enregistrement…" : "Enregistrer le brouillon"}
          </button>
          {saveError !== null && <ErrorMessage error={saveError} />}
          {notice && <p role="status">{notice}</p>}
        </form>
      )}
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
