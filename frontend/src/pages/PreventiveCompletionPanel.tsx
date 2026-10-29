import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import { ApiError, get, request } from "../api/client";
import { DataState, ErrorMessage } from "../components/common";
import { formatDateTime } from "../lib/time";

type MeterKind = "ODOMETER_KM" | "HOUR_METER";

interface ApprovalChoice {
  approval_id: string;
  cumulative_total: string | number;
  approved_at: string;
}

interface CompletionContext {
  maintenance_due_id: string;
  status: "SCHEDULED" | "COMPLETED";
  plan_code: string;
  closed_at: string;
  meters: {
    meter_kind: MeterKind;
    frozen_total: string | number | null;
    approvals: ApprovalChoice[];
  }[];
}

interface Props {
  order: {
    work_order_id: string;
    vehicle_id: string;
    kind: string;
    status: string;
  };
  allowed: boolean;
  timeZone: string;
}

const METERS: Record<MeterKind, string> = {
  ODOMETER_KM: "Kilométrage cumulé (km)",
  HOUR_METER: "Heures moteur cumulées (h)",
};

export function PreventiveCompletionPanel({ order, allowed, timeZone }: Props) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Partial<Record<MeterKind, string>>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [saving, setSaving] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const enabled = allowed && order.kind === "PREVENTIVE" && order.status === "CLOSED";
  const queryKey = ["preventive-completion", order.work_order_id];
  const context = useQuery({
    queryKey,
    queryFn: () => get<CompletionContext>(`/work-orders/${order.work_order_id}/preventive-completion`),
    enabled,
    retry: false,
  });
  if (!enabled) return null;
  const data = context.data;
  const ready = data?.meters.every((meter) =>
    meter.frozen_total !== null ||
    meter.approvals.some((approval) => approval.approval_id === selected[meter.meter_kind]),
  ) ?? false;

  async function complete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !data || data.status !== "SCHEDULED" || !ready || !confirmed || context.isFetching) return;
    submitting.current = true;
    setSaving(true);
    setError(null);
    setMessage(null);
    const body: { odometer_approval_id?: string; hour_meter_approval_id?: string } = {};
    for (const meter of data.meters) {
      if (meter.frozen_total !== null) continue;
      if (meter.meter_kind === "ODOMETER_KM") body.odometer_approval_id = selected.ODOMETER_KM;
      else body.hour_meter_approval_id = selected.HOUR_METER;
    }
    try {
      const response = await request<{ changed: boolean; status: "COMPLETED" }>(
        `/work-orders/${order.work_order_id}/complete-preventive`,
        { method: "POST", body },
      );
      queryClient.setQueryData<CompletionContext>(queryKey, { ...data, status: "COMPLETED" });
      setMessage(response.data.changed ? "Échéance préventive finalisée." : "Cette échéance était déjà finalisée.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["preventive-dues", order.vehicle_id] }),
        queryClient.invalidateQueries({ queryKey: ["preventive-completion", order.work_order_id] }),
      ]);
    } catch (failure) {
      setError(failure);
      setConfirmed(false);
      void context.refetch();
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  return (
    <section className="card" aria-label="Finalisation de l'entretien préventif">
      <h2>Finaliser l'échéance préventive</h2>
      <p className="muted">La clôture qualité de l'OT est acquise. Cette étape termine l'échéance du plan et fige ses preuves compteur.</p>
      {message && <p role="status">{message}</p>}
      {error !== null && <ErrorMessage error={error} />}
      {error instanceof ApiError && error.status === 409 && (
        <p role="alert">Le dossier ou les preuves ont changé. Vérifiez les choix actualisés avant de confirmer à nouveau.</p>
      )}
      <button type="button" disabled={saving || context.isFetching} onClick={() => void context.refetch()}>
        Actualiser les preuves
      </button>
      <DataState loading={context.isLoading} error={context.error} empty={!data}>
        {data && (
          <>
            <p>Plan : <strong>{data.plan_code}</strong> · Clôture : {formatDateTime(data.closed_at, timeZone)}</p>
            {data.status === "COMPLETED" ? (
              <p>Échéance terminée. Les preuves enregistrées sont figées.</p>
            ) : (
              <form onSubmit={(event) => void complete(event)} aria-label="Confirmer la finalisation préventive">
                <fieldset disabled={saving || context.isFetching}>
                  <legend>Preuves de l'entretien</legend>
                  {data.meters.length === 0 && <p>Plan calendaire : aucune preuve compteur requise.</p>}
                  {data.meters.map((meter) => (
                    <div key={meter.meter_kind}>
                      {meter.frozen_total !== null ? (
                        <p>{METERS[meter.meter_kind]} : {meter.frozen_total} — preuve déjà figée.</p>
                      ) : (
                        <>
                          <label>
                            {METERS[meter.meter_kind]}
                            <select required value={selected[meter.meter_kind] ?? ""} onChange={(event) => {
                              setSelected({ ...selected, [meter.meter_kind]: event.target.value });
                              setConfirmed(false);
                            }}>
                              <option value="">— Choisir une approbation —</option>
                              {meter.approvals.map((approval) => (
                                <option key={approval.approval_id} value={approval.approval_id}>
                                  {approval.cumulative_total} · approuvé le {formatDateTime(approval.approved_at, timeZone)}
                                </option>
                              ))}
                            </select>
                          </label>
                          {meter.approvals.length === 0 && (
                            <p role="alert">Aucune approbation utilisable à la clôture pour ce compteur. Faites examiner le dossier de réconciliation.</p>
                          )}
                        </>
                      )}
                    </div>
                  ))}
                  {data.meters.length > 0 && <p className="muted small">Jusqu'aux 25 approbations les plus récentes par compteur. Les preuves sont revérifiées à l'enregistrement.</p>}
                  <label className="checkbox">
                    <input type="checkbox" required checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                    Je confirme les preuves de cet entretien et la finalisation de son échéance.
                  </label>
                  <button type="submit" className="primary" disabled={saving || !ready || !confirmed || context.isFetching}>
                    {saving ? "Finalisation…" : "Finaliser l'échéance"}
                  </button>
                </fieldset>
              </form>
            )}
          </>
        )}
      </DataState>
    </section>
  );
}
