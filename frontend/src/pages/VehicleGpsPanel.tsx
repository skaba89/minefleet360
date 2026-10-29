import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { get, request } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";

interface Tracker { device_id: string; token?: string }

export function VehicleGpsPanel({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const manage = can(me.grants, "fleet.gps.manage", siteId);
  const tracker = useQuery({ queryKey: ["gps-tracker", vehicleId], queryFn: () => get<Tracker | null>(`/vehicles/${vehicleId}/gps/tracker`), enabled: manage });
  const [device, setDevice] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  async function provision(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null); setToken(null);
    try {
      const { data } = await request<Tracker>(`/vehicles/${vehicleId}/gps/tracker`, { method: "POST", body: { device_id: device } });
      setToken(data.token ?? null); await tracker.refetch();
    } catch (err) { setError(err); } finally { setBusy(false); }
  }
  async function revoke() {
    setBusy(true); setError(null); setToken(null);
    try { await request(`/vehicles/${vehicleId}/gps/tracker/revoke`, { method: "POST" }); setConfirmRevoke(false); await tracker.refetch(); }
    catch (err) { setError(err); } finally { setBusy(false); }
  }
  return <section className="card"><div className="page-head"><div><h2>Géolocalisation</h2><p className="muted small">Téléphone du compte ou traceur GPS du véhicule</p></div><Link to="/flotte-gps">Voir la flotte GPS →</Link></div>
    {can(me.grants, "fleet.gps.share", siteId) && <p><Link className="button-link" to={`/mon-suivi?vehicle=${vehicleId}`}>Partager mon téléphone pour ce véhicule</Link></p>}
    {manage && <>
      {tracker.isLoading ? <p role="status">Chargement du traceur…</p> : tracker.error ? <ErrorMessage error={tracker.error} /> : tracker.data ? <div className="toolbar"><span>Traceur associé : <strong>{tracker.data.device_id}</strong></span>{!confirmRevoke ? <button type="button" onClick={() => setConfirmRevoke(true)}>Révoquer l'accès</button> : <><button type="button" className="danger" disabled={busy} onClick={() => void revoke()}>Confirmer la révocation</button><button type="button" onClick={() => setConfirmRevoke(false)}>Annuler</button></>}</div> : <form className="inline" onSubmit={(e) => void provision(e)}><label>Identifiant du traceur<input required maxLength={120} pattern="[A-Za-z0-9][A-Za-z0-9_.:\-]*" value={device} onChange={(e) => setDevice(e.target.value)} placeholder="IMEI ou identifiant équipement" /></label><button className="primary" disabled={busy} type="submit">Associer un traceur</button></form>}
      {token && <div className="secret"><strong>Clé d'ingestion · affichée une seule fois</strong><p className="small">Transmettez cette clé uniquement à l'intégrateur du traceur. Elle donne accès à l'envoi de positions pour ce véhicule.</p><textarea readOnly aria-label="Clé d'ingestion du traceur" value={token} rows={3} /><button type="button" onClick={() => setToken(null)}>Masquer la clé</button></div>}
      <p className="muted small">Le traceur ou sa passerelle doit envoyer du JSON HTTPS à <code>/api/v1/gps/telemetry</code> avec cette clé en en-tête Bearer. Les protocoles propriétaires nécessitent un adaptateur ; associer l'identifiant seul ne connecte pas le matériel.</p>
      {error !== null && <ErrorMessage error={error} />}
    </>}
  </section>;
}
