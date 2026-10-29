import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { get, request } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";

export function DriverGpsAccount({ driverId }: { driverId: string }) {
  const me = useMe();
  const permitted = can(me.grants, "workforce.driver.link_account");
  const account = useQuery({ queryKey: ["gps-driver-account", driverId], queryFn: () => get<{ user_account_id: string | null }>(`/drivers/${driverId}/gps-account`), enabled: permitted });
  const users = useQuery({ queryKey: ["gps-driver-users"], queryFn: () => get<{ items: { user_account_id: string; display_name: string; status: string }[] }>("/users", { page_size: 200 }), enabled: permitted });
  const [value, setValue] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!permitted) return null;
  return <section className="card"><h2>Compte du conducteur pour le GPS</h2><p className="muted">Le compte doit être actif et disposer du rôle Conducteur sur ce site. Il pourra ensuite partager son téléphone pour son véhicule en affectation active.</p><form className="inline" onSubmit={(e) => {
    e.preventDefault(); setBusy(true); setError(null);
    void request(`/drivers/${driverId}/gps-account`, { method: "POST", body: { user_account_id: (value ?? account.data?.user_account_id) || null } }).then(() => account.refetch()).catch(setError).finally(() => setBusy(false));
  }}><label>Compte lié<select value={value ?? account.data?.user_account_id ?? ""} onChange={(e) => setValue(e.target.value)} disabled={account.isLoading || users.isLoading || busy}><option value="">Aucun compte lié</option>{users.data?.items.filter((u) => u.status === "ACTIVE").map((u) => <option key={u.user_account_id} value={u.user_account_id}>{u.display_name}</option>)}</select></label><button type="submit" className="primary" disabled={busy || !account.isSuccess || !users.isSuccess}>Enregistrer le lien</button></form>{(error || account.error || users.error) ? <ErrorMessage error={error || account.error || users.error} /> : null}</section>;
}
