import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { get, request } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";

interface PreventiveDue {
  maintenance_due_id: string;
  maintenance_plan_id: string;
  status: "DUE" | "SCHEDULED" | "COMPLETED" | "CANCELLED";
  trigger_kind: "KM" | "HOURS" | "DAYS";
  due_on: string | null;
  due_meter: number | string | null;
  work_order_id: string | null;
}

export function VehiclePreventiveDues({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const allowed = can(me.grants, "maintenance.preventive.read", siteId);
  const maySchedule = can(me.grants, "maintenance.preventive.manage", siteId);
  const dues = useQuery({
    queryKey: ["preventive-dues", vehicleId],
    queryFn: () => get<PreventiveDue[]>(`/vehicles/${vehicleId}/preventive-dues`),
    enabled: allowed,
  });

  if (!allowed) return null;

  async function schedule(dueId: string) {
    setPending(dueId);
    setError(null);
    try {
      await request<{ work_order_id: string }>(`/preventive-dues/${dueId}/schedule`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["preventive-dues", vehicleId] });
      await queryClient.invalidateQueries({ queryKey: ["work-orders"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(null);
    }
  }

  return (
    <section aria-label="Maintenance préventive">
      <h2>Échéances de maintenance préventive</h2>
      {error && <ErrorMessage error={error} />}
      <DataState loading={dues.isLoading} error={dues.error} empty={!dues.data?.length} emptyText="Aucune échéance préventive.">
        <table>
          <thead>
            <tr>
              <th scope="col">Déclencheur</th>
              <th scope="col">Échéance</th>
              <th scope="col">Statut</th>
              <th scope="col">Ordre de travail</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {(dues.data ?? []).map((due) => (
              <tr key={due.maintenance_due_id}>
                <td>{due.trigger_kind}</td>
                <td>{due.due_on ?? due.due_meter ?? "—"}</td>
                <td>{due.status}</td>
                <td>
                  {due.work_order_id ? <Link to={`/atelier/${due.work_order_id}`}>Voir l'OT</Link> : "—"}
                </td>
                <td>
                  {maySchedule && due.status === "DUE" && !due.work_order_id && (
                    <button
                      type="button"
                      disabled={pending !== null}
                      onClick={() => void schedule(due.maintenance_due_id)}
                    >
                      {pending === due.maintenance_due_id ? "Planification…" : "Planifier l'entretien"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}
