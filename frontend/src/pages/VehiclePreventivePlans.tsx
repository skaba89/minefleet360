import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { get, request } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";

interface PreventivePlan {
  maintenance_plan_id: string;
  code: string;
  version: number;
  km_interval: string | number | null;
  hours_interval: string | number | null;
  days_interval: number | null;
  active: boolean;
  suspension_reason: string | null;
  row_version: number;
}

export function VehiclePreventivePlans({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [days, setDays] = useState("");
  const [kilometers, setKilometers] = useState("");
  const [hours, setHours] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const allowed = can(me.grants, "maintenance.preventive.read", siteId);
  const managing = can(me.grants, "maintenance.preventive.manage", siteId);
  const plans = useQuery({
    queryKey: ["preventive-plans", vehicleId],
    queryFn: () => get<PreventivePlan[]>(`/vehicles/${vehicleId}/preventive-plans`),
    enabled: allowed,
  });

  if (!allowed) return null;

  async function createPlan(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await request("/preventive-plans", {
        method: "POST",
        body: {
          vehicle_id: vehicleId,
          code: code.trim(),
          days_interval: days ? Number(days) : null,
          km_interval: kilometers || null,
          hours_interval: hours || null,
        },
      });
      setCode("");
      setDays("");
      setKilometers("");
      setHours("");
      await queryClient.invalidateQueries({ queryKey: ["preventive-plans", vehicleId] });
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-label="Plans de maintenance préventive">
      <h2>Plans de maintenance préventive</h2>
      {error != null ? <ErrorMessage error={error} /> : null}
      <DataState loading={plans.isLoading} error={plans.error} empty={!plans.data?.length} emptyText="Aucun plan préventif.">
        <table>
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Version</th>
              <th scope="col">Périodicités</th>
              <th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            {(plans.data ?? []).map((plan) => (
              <tr key={plan.maintenance_plan_id}>
                <td>{plan.code}</td>
                <td>{plan.version}</td>
                <td>
                  {[
                    plan.days_interval ? `${plan.days_interval} jours` : null,
                    plan.km_interval != null ? `${plan.km_interval} km` : null,
                    plan.hours_interval != null ? `${plan.hours_interval} h` : null,
                  ].filter(Boolean).join(" · ")}
                </td>
                <td>{plan.active ? "Actif" : `Suspendu — ${plan.suspension_reason ?? "sans motif"}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
      {managing && (
        <form onSubmit={(event) => void createPlan(event)}>
          <h3>Créer un plan</h3>
          <div className="filters">
            <label>
              Code du plan
              <input required maxLength={80} pattern="[A-Za-z0-9][A-Za-z0-9_.-]*" value={code} onChange={(event) => setCode(event.target.value)} />
            </label>
            <label>
              Jours
              <input type="number" min="1" max="36500" value={days} onChange={(event) => setDays(event.target.value)} />
            </label>
            <label>
              Kilomètres
              <input type="number" min="0.1" step="0.1" value={kilometers} onChange={(event) => setKilometers(event.target.value)} />
            </label>
            <label>
              Heures moteur
              <input type="number" min="0.1" step="0.1" value={hours} onChange={(event) => setHours(event.target.value)} />
            </label>
          </div>
          <button type="submit" disabled={saving || (!days && !kilometers && !hours)}>
            {saving ? "Enregistrement…" : "Créer le plan"}
          </button>
        </form>
      )}
    </section>
  );
}
