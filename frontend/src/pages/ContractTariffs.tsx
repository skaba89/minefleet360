import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ActionForm, orNull } from "../components/forms";
import { can } from "../lib/permissions";

type Tariff = Schemas["TariffOut"];
type Basis = Tariff["basis"];

export const BASIS_LABEL: Record<Basis, string> = {
  TONNE: "par tonne mesurée",
  HOUR: "par heure moteur",
  KM: "par km",
  MISSION: "forfait par mission",
};

function price(value: string, currency: string): string {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(Number(value))} ${currency}`;
}

/** Tarifs des contrats de transport approuvés (contrôle de gestion, tranche 2a) : versions datées, ajout seul. */
export function ContractTariffsSection() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [entering, setEntering] = useState(false);
  const contracts = useQuery({ queryKey: ["billable-contracts"], queryFn: () => read("/contract-tariffs/contracts") });
  const tariffs = useQuery({ queryKey: ["contract-tariffs"], queryFn: () => read("/contract-tariffs") });
  const reference = new Map((contracts.data ?? []).map((c) => [c.contract_id, `${c.reference} — ${c.counterparty_name}`]));
  const rows = tariffs.data ?? [];
  return (
    <section aria-label="Tarifs des contrats">
      <div className="page-head">
        <h2>Tarifs des contrats de transport</h2>
        {can(me.grants, "finance.tariff.manage") && !entering && (
          <button type="button" className="primary" onClick={() => setEntering(true)} disabled={!contracts.data?.length}>
            Saisir un tarif
          </button>
        )}
      </div>
      {entering && (
        <TariffForm
          contracts={contracts.data ?? []}
          onCancel={() => setEntering(false)}
          onDone={() => {
            setEntering(false);
            void queryClient.invalidateQueries({ queryKey: ["contract-tariffs"] });
          }}
        />
      )}
      <DataState loading={tariffs.isLoading} error={tariffs.error} empty={rows.length === 0} emptyText="Aucun tarif saisi.">
        <table>
          <thead>
            <tr>
              <th scope="col">Contrat</th>
              <th scope="col">Tarif</th>
              <th scope="col">En vigueur depuis</th>
              <th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.contract_tariff_id}>
                <td>{reference.get(t.contract_id) ?? t.contract_id}</td>
                <td>
                  {price(t.unit_price, t.currency)} {BASIS_LABEL[t.basis]}
                </td>
                <td>{t.valid_from}</td>
                <td>{t.current ? <Badge tone="ok">En vigueur</Badge> : <span className="small muted">Historique ou à venir</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      <p className="muted small">
        Seuls les contrats de transport approuvés acceptent un tarif. Le revenu sera calculé sur les quantités mesurées
        (pesées valides, horamètre, odomètre), jamais estimées.
      </p>
    </section>
  );
}

function TariffForm({
  contracts,
  onCancel,
  onDone,
}: {
  contracts: Schemas["BillableContractOut"][];
  onCancel: () => void;
  onDone: () => void;
}) {
  const me = useMe();
  const allowed = contracts.filter((c) => can(me.grants, "finance.tariff.manage", c.site_id));
  const [form, setForm] = useState({
    contract_id: allowed[0]?.contract_id ?? "",
    basis: "TONNE" as Basis,
    unit_price: "",
    currency: "GNF",
    valid_from: new Date().toISOString().slice(0, 10),
    note: "",
  });
  return (
    <ActionForm
      title="Saisir un tarif"
      submitLabel="Enregistrer le tarif"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/contract-tariffs", {
          body: { ...form, currency: form.currency.trim().toUpperCase(), note: orNull(form.note) },
        })
      }
    >
      <label>
        Contrat
        <select required value={form.contract_id} onChange={(e) => setForm({ ...form, contract_id: e.target.value })}>
          {allowed.map((c) => (
            <option key={c.contract_id} value={c.contract_id}>
              {c.reference} — {c.counterparty_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Mode de tarification
        <select value={form.basis} onChange={(e) => setForm({ ...form, basis: e.target.value as Basis })}>
          {(Object.keys(BASIS_LABEL) as Basis[]).map((b) => (
            <option key={b} value={b}>
              {BASIS_LABEL[b]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Prix unitaire
        <input type="number" required min={0} step="0.0001" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: e.target.value })} />
      </label>
      <label>
        Devise (ISO)
        <input required pattern="[A-Za-z]{3}" maxLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
      </label>
      <label>
        En vigueur à partir du
        <input type="date" required value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
      </label>
      <label>
        Commentaire (facultatif)
        <input maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
      </label>
      <p className="muted small">Une révision crée une nouvelle version datée ; les précédentes restent dans l'historique.</p>
    </ActionForm>
  );
}
