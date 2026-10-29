import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { ApiError, get, request } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { DataState, ErrorMessage } from "../components/common";
import { Icon } from "../components/Icon";
import { can } from "../lib/permissions";
import { formatDateTime } from "../lib/time";

interface VehicleOption { vehicle_id: string; fleet_number: string; registration_number: string | null; site_id: string }
interface VehiclePage { items: VehicleOption[]; page: number; page_size: number; total: number }
interface Share { phone_share_id: string; vehicle_id: string; started_at: string; expires_at: string }

export function PhoneTrackingPage() {
  const me = useMe();
  const [params] = useSearchParams();
  const permitted = can(me.grants, "fleet.gps.share");
  const [vehiclePage, setVehiclePage] = useState(1);
  const vehicles = useQuery({
    queryKey: ["gps-sharing-vehicles", vehiclePage],
    queryFn: async () => {
      const pages = await Promise.all(Array.from({ length: vehiclePage }, (_, index) =>
        get<VehiclePage>("/me/gps/vehicles", { page: index + 1, page_size: 50 }),
      ));
      return { items: pages.flatMap((page) => page.items), total: pages[0]?.total ?? 0 };
    },
    enabled: permitted,
  });
  const [vehicleId, setVehicleId] = useState(params.get("vehicle") ?? "");
  const [consent, setConsent] = useState(false);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("Partage désactivé");
  const [lastSent, setLastSent] = useState<string | null>(null);
  const [expires, setExpires] = useState<string | null>(null);
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const share = useRef<Share | null>(null);
  const active = useRef(false);

  useEffect(() => () => {
    generation.current++;
    active.current = false;
    clearTimeout(timer.current);
    const current = share.current;
    if (current) void request(`/me/gps/shares/${current.phone_share_id}/stop`, { method: "POST" }).catch(() => undefined);
  }, []);

  async function stop() {
    generation.current++;
    active.current = false;
    clearTimeout(timer.current);
    setRunning(false);
    setMessage("GPS du téléphone arrêté");
    setBusy(true);
    setError(null);
    try {
      if (share.current) await request(`/me/gps/shares/${share.current.phone_share_id}/stop`, { method: "POST" });
      share.current = null;
      setExpires(null);
      setMessage("Partage arrêté et confirmé par le serveur");
    } catch (err) {
      setError(err);
      setMessage("GPS arrêté sur ce téléphone. L'arrêt serveur reste à confirmer.");
    } finally { setBusy(false); }
  }

  async function start() {
    if (!navigator.geolocation || !window.isSecureContext) {
      setError(new ApiError(0, { code: "GPS_UNAVAILABLE", message_fr: "La localisation nécessite un navigateur compatible et une connexion HTTPS.", details: null, request_id: null }));
      return;
    }
    const run = ++generation.current;
    setBusy(true); setError(null); setLastSent(null);
    try {
      const { data } = await request<Share>("/me/gps/shares", { method: "POST", body: { vehicle_id: vehicleId, consent } });
      if (generation.current !== run) {
        void request(`/me/gps/shares/${data.phone_share_id}/stop`, { method: "POST" }).catch(() => undefined);
        return;
      }
      share.current = data;
      active.current = true;
      setExpires(data.expires_at);
      setRunning(true);
      setMessage("Autorisez la localisation dans votre navigateur…");
      const sample = () => {
        if (generation.current !== run || !active.current) return;
        navigator.geolocation.getCurrentPosition((position) => {
          if (generation.current !== run || !active.current) return;
          const { latitude, longitude, accuracy, speed } = position.coords;
          const speedKmh = speed !== null && Number.isFinite(speed) && speed >= 0 && speed <= 250 / 3.6 ? speed * 3.6 : null;
          const recorded = new Date(position.timestamp).toISOString();
          void request(`/me/gps/shares/${data.phone_share_id}/positions`, { method: "POST", body: {
            latitude, longitude, accuracy_m: accuracy, speed_kmh: speedKmh, recorded_at: recorded,
          } }).then(() => {
            if (generation.current !== run) return;
            setLastSent(recorded); setError(null); setMessage(`Partage actif · précision ±${Math.round(accuracy)} m`);
          }).catch((err: unknown) => {
            if (generation.current !== run) return;
            setError(err); setMessage("Position non transmise. La dernière position peut devenir ancienne.");
            if (err instanceof ApiError && [401, 403, 404, 409].includes(err.status)) void stop().then(() => setError(err));
          }).finally(() => {
            if (generation.current === run && active.current) timer.current = setTimeout(sample, 10_000);
          });
        }, (failure) => {
          if (generation.current !== run) return;
          if (failure.code === 1) {
            void stop().then(() => setError(new ApiError(0, { code: "GPS_DENIED", message_fr: "Localisation refusée. Autorisez-la dans les réglages du navigateur pour reprendre.", details: null, request_id: null })));
          } else {
            setMessage("Signal GPS indisponible. Nouvelle tentative dans 10 secondes.");
            timer.current = setTimeout(sample, 10_000);
          }
        }, { enableHighAccuracy: true, maximumAge: 0, timeout: 15_000 });
      };
      sample();
    } catch (err) { if (generation.current === run) setError(err); }
    finally { if (generation.current === run) setBusy(false); }
  }

  if (!permitted) return <p>Votre compte ne peut pas partager de position.</p>;
  const vehicleOptions = Array.isArray(vehicles.data) ? vehicles.data : vehicles.data?.items ?? [];
  const vehicleTotal = Array.isArray(vehicles.data) ? vehicles.data.length : vehicles.data?.total ?? 0;
  const chosen = vehicleOptions.find((v) => v.vehicle_id === vehicleId);
  return <section>
    <div className="page-head"><div><h1>Mon partage GPS</h1><p className="muted">Localiser le véhicule avec le téléphone de votre compte</p></div><span className={`badge badge-${running ? "ok" : "neutral"}`}><Icon name="phone" /> {running ? "Partage actif" : "Désactivé"}</span></div>
    <div className="card tracking-card">
      <h2>Partager la position de ce téléphone</h2>
      <p>La position de ce téléphone représentera le véhicule choisi. Activez le partage uniquement lorsque vous êtes à bord.</p>
      <DataState loading={vehicles.isLoading} error={vehicles.error} empty={vehicleOptions.length === 0} emptyText="Aucun véhicule autorisé. Pour un conducteur, l'administrateur doit relier son compte au dossier conducteur et une affectation doit être active.">
        <label>Véhicule<select value={vehicleId} disabled={running || busy} onChange={(e) => { setVehicleId(e.target.value); setConsent(false); }}><option value="">Choisir un véhicule</option>{vehicleOptions.map((v) => <option key={v.vehicle_id} value={v.vehicle_id}>{v.fleet_number}{v.registration_number ? ` · ${v.registration_number}` : ""}</option>)}</select></label>
        {vehicleOptions.length < vehicleTotal && <button type="button" disabled={vehicles.isFetching} onClick={() => setVehiclePage((page) => page + 1)}>{vehicles.isFetching ? "Chargement…" : `Charger la suite (${vehicleOptions.length} sur ${vehicleTotal})`}</button>}
        <label className="checkbox"><input type="checkbox" checked={consent} disabled={running || busy} onChange={(e) => setConsent(e.target.checked)} />Je suis à bord et j'accepte de partager la position de ce téléphone pour ce véhicule.</label>
        <div className="toolbar">{!running && <button className="primary" type="button" disabled={busy || !consent || !chosen} onClick={() => void start()}>Démarrer le partage</button>}</div>
      </DataState>
      {(running || share.current) && <div className="toolbar"><button className="danger" type="button" disabled={busy} onClick={() => void stop()}>Arrêter le partage</button></div>}
      <p role="status" className={running ? "success" : "muted"}>{message}</p>
      {error !== null && <ErrorMessage error={error} />}
      {lastSent && <p className="small">Dernier relevé transmis : {formatDateTime(lastSent, me.timezone)} ({me.timezone})</p>}
      {expires && <p className="small muted">Expiration au plus tard : {formatDateTime(expires, me.timezone)}. La session du compte doit rester active.</p>}
    </div>
    <div className="card"><h2>Pour garder un suivi fiable</h2><p>Gardez cette page ouverte, le téléphone à bord et le réseau disponible. Les relevés sont demandés environ toutes les 10 secondes ; la supervision se rafraîchit toutes les 15 secondes.</p><p className="muted">Le navigateur peut suspendre le GPS quand l'écran est verrouillé ou l'application en arrière-plan. Pour un suivi autonome et permanent, utilisez un traceur GPS compatible avec l'API d'ingestion.</p><p className="small">Quitter cette page coupe les relevés sur le téléphone. Si le réseau empêche de confirmer l'arrêt, les coordonnées déjà reçues restent affichées avec leur date ; elles deviennent anciennes après 2 minutes.</p></div>
  </section>;
}
