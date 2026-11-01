import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage, Pager } from "../components/common";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";
import { StorageReconciliationPanel } from "./StorageReconciliationPanel";

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
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [reviewAction, setReviewAction] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [reviewNote, setReviewNote] = useState("");
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<unknown>(null);
  const [reviewNotice, setReviewNotice] = useState("");
  const [policyNumber, setPolicyNumber] = useState("");
  const [insurer, setInsurer] = useState("");
  const [coverageType, setCoverageType] = useState<Schemas["InsurancePolicyInput"]["coverage_type"]>("FLEET");
  const [coverageStart, setCoverageStart] = useState("");
  const [coverageEnd, setCoverageEnd] = useState("");
  const [policySaving, setPolicySaving] = useState(false);
  const [policyError, setPolicyError] = useState<unknown>(null);
  const [policyNotice, setPolicyNotice] = useState("");
  const { siteId } = useSites();
  const [tab, setTab] = useState<LegalTab>("contracts");
  const [page, setPage] = useState(1);
  const canReadContracts = can(me.grants, "legal.contract.read", siteId);
  const canCreateContract = Boolean(siteId) && can(me.grants, "legal.contract.create", siteId);
  const canReviewContract = can(me.grants, "legal.contract.review", siteId);
  const canReadPolicies = can(me.grants, "legal.insurance.read", siteId);
  const canCreatePolicy = Boolean(siteId) && can(me.grants, "legal.insurance.create", siteId);
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
      {canReadContracts && <StorageReconciliationPanel />}
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
      {activeTab === "insurance" && canCreatePolicy && siteId && (
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (policySaving || coverageEnd < coverageStart) return;
          setPolicySaving(true);
          setPolicyError(null);
          setPolicyNotice("");
          try {
            await call("post", "/insurance-policies", {
              body: {
                site_id: siteId,
                policy_number: policyNumber.trim(),
                insurer_name: insurer.trim(),
                coverage_type: coverageType,
                coverage_start: coverageStart,
                coverage_end: coverageEnd,
                currency: "GNF",
              },
            });
            setPolicyNumber("");
            setInsurer("");
            setCoverageStart("");
            setCoverageEnd("");
            setPage(1);
            await queryClient.invalidateQueries({ queryKey: ["insurance-policies"] });
            setPolicyNotice("Police enregistrée. Vérifiez les documents auprès de votre assureur.");
          } catch (error) {
            setPolicyError(error);
          } finally {
            setPolicySaving(false);
          }
        }}>
          <h2>Nouvelle police d'assurance</h2>
          <label>Numéro de police <input required maxLength={120} value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} /></label>
          <label>Assureur <input required maxLength={240} value={insurer} onChange={(e) => setInsurer(e.target.value)} /></label>
          <label>Type de couverture
            <select value={coverageType} onChange={(e) => setCoverageType(e.target.value as Schemas["InsurancePolicyInput"]["coverage_type"])}>
              <option value="FLEET">Flotte</option>
              <option value="VEHICLE">Véhicule</option>
              <option value="CARGO">Marchandises</option>
              <option value="LIABILITY">Responsabilité civile</option>
              <option value="EMPLOYEE">Salariés</option>
              <option value="EQUIPMENT">Équipements</option>
              <option value="OTHER">Autre</option>
            </select>
          </label>
          <label>Début de couverture <input type="date" required value={coverageStart} onChange={(e) => setCoverageStart(e.target.value)} /></label>
          <label>Fin de couverture <input type="date" required min={coverageStart || undefined} value={coverageEnd} onChange={(e) => setCoverageEnd(e.target.value)} /></label>
          <button type="submit" disabled={policySaving || !policyNumber.trim() || !insurer.trim() || !coverageStart || !coverageEnd || coverageEnd < coverageStart}>
            {policySaving ? "Enregistrement…" : "Enregistrer la police"}
          </button>
          {policyError !== null && <ErrorMessage error={policyError} />}
          {policyNotice && <p role="status">{policyNotice}</p>}
        </form>
      )}
      {activeTab === "contracts" && reviewId && canReviewContract && (
        <form onSubmit={async (event) => {
          event.preventDefault();
          if (reviewSaving || !reviewNote.trim()) return;
          setReviewSaving(true);
          setReviewError(null);
          setReviewNotice("");
          try {
            await call("post", "/legal-contracts/{contract_id}/decision", {
              path: { contract_id: reviewId },
              body: { action: reviewAction, note: reviewNote.trim() },
            });
            setReviewId(null);
            setReviewNote("");
            await queryClient.invalidateQueries({ queryKey: ["legal-contracts"] });
            setReviewNotice("Décision enregistrée. Elle ne constitue pas une signature électronique.");
          } catch (error) {
            setReviewError(error);
          } finally {
            setReviewSaving(false);
          }
        }}>
          <h2>Décision sur le contrat</h2>
          <p>Contrat sélectionné : {contracts.data?.items.find((item: Contract) => item.contract_id === reviewId)?.reference ?? reviewId}</p>
          <label>Décision
            <select value={reviewAction} onChange={(event) => setReviewAction(event.target.value as "APPROVE" | "REJECT")}>
              <option value="APPROVE">Approuver</option>
              <option value="REJECT">Rejeter</option>
            </select>
          </label>
          <label>Motif de la décision
            <textarea required maxLength={500} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
          </label>
          <button type="submit" disabled={reviewSaving || !reviewNote.trim()}>{reviewSaving ? "Enregistrement…" : "Confirmer la décision"}</button>
          <button type="button" disabled={reviewSaving} onClick={() => { setReviewId(null); setReviewError(null); }}>Annuler</button>
          {reviewError !== null && <ErrorMessage error={reviewError} />}
        </form>
      )}
      {activeTab === "contracts" && reviewNotice && <p role="status">{reviewNotice}</p>}
      {!allowed ? <p className="error" role="alert">Accès non autorisé pour ce registre.</p> : (
        <DataState loading={current.isLoading} error={current.error} empty={!current.data?.items.length}>
          {activeTab === "contracts" ? (
            <table>
              <thead><tr><th>Référence</th><th>Intitulé</th><th>Type</th><th>Contrepartie</th><th>Statut</th>{canReviewContract && <th>Décision</th>}</tr></thead>
              <tbody>{(contracts.data?.items ?? []).map((item: Contract) => (
                <tr key={item.contract_id}><td>{item.reference}</td><td>{item.title}</td><td>{item.contract_type}</td><td>{item.counterparty_name}</td><td>{item.status}</td>{canReviewContract && <td>{item.status === "PENDING_REVIEW" && <button type="button" onClick={() => { setReviewId(item.contract_id); setReviewAction("APPROVE"); setReviewNote(""); setReviewError(null); setReviewNotice(""); }}>Examiner</button>}</td>}</tr>
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
