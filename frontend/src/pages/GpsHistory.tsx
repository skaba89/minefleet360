import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import { label } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Track = Schemas["TrackOut"];
type Purpose = "OPERATIONS_REVIEW" | "INCIDENT_INVESTIGATION" | "MAINTENANCE_DIAGNOSIS" | "SECURITY" | "CLIENT_DISPUTE";

const PURPOSES: Record<string, string> = {
  INCIDENT_INVESTIGATION: "Enquête sur un incident",
  OPERATIONS_REVIEW: "Analyse d'exploitation",
  MAINTENANCE_DIAGNOSIS: "Diagnostic de maintenance",
  SECURITY: "Sûreté",
  CLIENT_DISPUTE: "Litige client",
};
export const GEOFENCE_KIND: Record<string, string> = {
  SITE_BOUNDARY: "Limite de site",
  LOADING_AREA: "Zone de chargement",
  DUMP_AREA: "Zone de déchargement",
  WORKSHOP: "Atelier",
  FUEL_STATION: "Station carburant",
  RESTRICTED: "Zone interdite",
  OTHER: "Autre",
};
const SIGNAL: Record<string, string> = { FRESH: "Signal récent", STALE: "Signal ancien", LOST: "Signal perdu", NONE: "Aucune position" };
const SIGNAL_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = { FRESH: "ok", STALE: "warn", LOST: "bad", NONE: "neutral" };

/** Tracé schématique (projection plate locale) : aucun fond de carte, aucune donnée envoyée à un tiers. */
function TrackSketch({ track }: { track: Track }) {
  const points = track.points;
  if (points.length < 2) return null;
  const lats = points.map((p) => p.latitude);
  const lons = points.map((p) => p.longitude);
  const [minLat, maxLat, minLon, maxLon] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)];
  const span = Math.max(maxLat - minLat, maxLon - minLon) || 1e-6;
  const xy = (p: { latitude: number; longitude: number }) =>
    `${(((p.longitude - minLon) / span) * 280 + 10).toFixed(1)},${(290 - ((p.latitude - minLat) / span) * 280).toFixed(1)}`;
  return (
    <svg viewBox="0 0 300 300" width="300" height="300" role="img" aria-label="Tracé schématique du trajet">
      <rect x="0" y="0" width="300" height="300" fill="none" stroke="currentColor" strokeOpacity="0.2" />
      <polyline points={points.map(xy).join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5" />
      {track.stops.map((s) => {
        const [x, y] = xy(s).split(",");
        return <circle key={s.start} cx={x} cy={y} r="5" fill="none" stroke="currentColor" />;
      })}
    </svg>
  );
}

/** Historique de trajet d'un engin : finalité obligatoire, consultation tracée dans le journal d'audit. */
export function VehicleTrackPanel({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const { timezoneOf } = useSites();
  const tz = timezoneOf(siteId);
  const now = new Date();
  const [form, setForm] = useState({
    purpose: "",
    from: utcToZonedInput(new Date(now.getTime() - 6 * 3600_000), tz),
    to: utcToZonedInput(now, tz),
  });
  const [track, setTrack] = useState<Track | null>(null);
  if (!can(me.grants, "fleet.gps.history", siteId)) return null;
  return (
    <section aria-label="Historique de trajet">
      <h2>Historique de trajet</h2>
      <p className="muted small">
        Données de localisation sensibles : indiquez la finalité ; chaque consultation est enregistrée dans le journal d'audit.
        24 heures maximum. Un suivi par téléphone n'est pas continu en arrière-plan : les interruptions sont affichées.
      </p>
      <ActionForm
        title="Consulter le trajet"
        submitLabel="Afficher le trajet"
        onSubmit={async () => {
          const { data } = await call("get", "/vehicles/{vehicle_id}/gps/track", {
            path: { vehicle_id: vehicleId },
            query: {
              purpose: form.purpose as Purpose,
              from: zonedInputToUtc(form.from, tz).toISOString(),
              to: zonedInputToUtc(form.to, tz).toISOString(),
            },
          });
          setTrack(data);
        }}
      >
        <label>
          Finalité
          <select required value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}>
            <Options map={PURPOSES} empty="— Choisir —" />
          </select>
        </label>
        <label>
          Du (heure du site)
          <input type="datetime-local" required value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} />
        </label>
        <label>
          Au
          <input type="datetime-local" required value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} />
        </label>
      </ActionForm>
      {track && (
        <div className="card">
          <p>
            <Badge tone={SIGNAL_TONE[track.signal] ?? "neutral"}>{SIGNAL[track.signal]}</Badge>{" "}
            {track.last_recorded_at && <span className="muted">dernière position {formatDateTime(track.last_recorded_at, tz)}</span>}
          </p>
          <ul>
            <li>{track.points.length} position(s){track.truncated ? " (limite de 5 000 atteinte : réduire la période)" : ""}</li>
            <li>Distance mesurée : {track.distance_km.toLocaleString("fr-FR", { maximumFractionDigits: 2 })} km</li>
            <li>{track.ignored_points} position(s) écartée(s) (imprécision supérieure à 100 m ou saut incohérent)</li>
            <li>{track.late_points} position(s) reçue(s) en retard</li>
          </ul>
          <TrackSketch track={track} />
          <h3>Entrées et sorties de zones</h3>
          {track.geofence_events.length === 0 ? (
            <p className="muted">Aucune.</p>
          ) : (
            <ul>
              {track.geofence_events.map((e, i) => (
                <li key={i}>
                  {formatDateTime(e.occurred_at, tz)} — {e.event_type === "ENTER" ? "Entrée" : "Sortie"} : {e.geofence_name} (
                  {label(GEOFENCE_KIND, e.geofence_kind)})
                </li>
              ))}
            </ul>
          )}
          <h3>Immobilisations (≥ 15 min)</h3>
          {track.stops.length === 0 ? (
            <p className="muted">Aucune.</p>
          ) : (
            <ul>
              {track.stops.map((s) => (
                <li key={s.start}>
                  {formatDateTime(s.start, tz)} → {formatDateTime(s.end, tz)} ({s.minutes} min)
                </li>
              ))}
            </ul>
          )}
          <h3>Interruptions de réception (&gt; 10 min)</h3>
          {track.gaps.length === 0 ? (
            <p className="muted">Aucune.</p>
          ) : (
            <ul>
              {track.gaps.map((g) => (
                <li key={g.start}>
                  {formatDateTime(g.start, tz)} → {formatDateTime(g.end, tz)} ({g.minutes} min sans position)
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

/** Zones (géofences) d'un site : liste, création par coordonnées, désactivation. */
export function GeofencesPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, sites } = useSites();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const fences = useQuery({
    queryKey: ["geofences", siteId],
    queryFn: () => read("/geofences", { query: { site_id: siteId } }),
  });
  const manage = can(me.grants, "fleet.geofence.manage", siteId);
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const reload = () => {
    setCreating(false);
    void queryClient.invalidateQueries({ queryKey: ["geofences"] });
  };
  return (
    <section>
      <div className="page-head">
        <h1>Zones de site (géofences)</h1>
        {manage && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouvelle zone
          </button>
        )}
      </div>
      {creating && <GeofenceForm onCancel={() => setCreating(false)} onDone={reload} />}
      {error !== null && <ErrorMessage error={error} />}
      <DataState loading={fences.isLoading} error={fences.error} empty={(fences.data ?? []).length === 0} emptyText="Aucune zone.">
        <table>
          <thead>
            <tr>
              <th scope="col">Zone</th>
              <th scope="col">Type</th>
              <th scope="col">Surface</th>
              <th scope="col">
                <span className="small">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {(fences.data ?? []).map((g) => (
              <tr key={g.site_geofence_id}>
                <td>
                  {g.name}
                  <div className="small muted">
                    {siteCode.get(g.site_id)} — {g.code} — {g.coordinates.length - 1} sommets
                  </div>
                </td>
                <td>{label(GEOFENCE_KIND, g.kind)}</td>
                <td>{(g.area_m2 / 10_000).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} ha</td>
                <td>
                  {manage && (
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        call("post", "/geofences/{site_geofence_id}/deactivate", { path: { site_geofence_id: g.site_geofence_id } })
                          .then(reload)
                          .catch(setError);
                      }}
                    >
                      Désactiver
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

/** Coordonnées saisies une par ligne « latitude, longitude » (ordre habituel des relevés terrain). */
export function parseCoordinates(text: string): [number, number][] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [lat, lon] = line.split(/[;,\s]+/).map(Number);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error(`Ligne invalide : « ${line} »`);
      return [lon!, lat!];
    });
}

function GeofenceForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const me = useMe();
  const { siteId, sites } = useSites();
  const allowed = sites.filter((s) => can(me.grants, "fleet.geofence.manage", s.site_id));
  const [form, setForm] = useState({ site_id: siteId ?? allowed[0]?.site_id ?? "", code: "", name: "", kind: "LOADING_AREA", points: "" });
  return (
    <ActionForm
      title="Nouvelle zone"
      submitLabel="Enregistrer la zone"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/geofences", {
          body: {
            site_id: form.site_id,
            code: form.code.trim(),
            name: form.name.trim(),
            kind: form.kind as Schemas["GeofenceCreate"]["kind"],
            coordinates: parseCoordinates(form.points),
          },
        })
      }
    >
      <label>
        Site
        <select required value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
          {allowed.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Code
        <input required pattern="[A-Za-z0-9_-]{1,48}" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
      </label>
      <label>
        Nom
        <input required minLength={2} maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </label>
      <label>
        Type
        <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
          <Options map={GEOFENCE_KIND} />
        </select>
      </label>
      <label>
        Sommets (une ligne « latitude, longitude » par sommet, 3 minimum)
        <textarea required rows={6} value={form.points} onChange={(e) => setForm({ ...form, points: e.target.value })} />
      </label>
    </ActionForm>
  );
}
