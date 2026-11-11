import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { get, request, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { AccessDenied, DataState, ErrorMessage } from "../components/common";
import { can } from "../lib/permissions";
import { formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Alert = Schemas["GpsAlertOut"];
type Policy = Schemas["GpsPolicyOut"];

export const ALERT_KIND: Record<Alert["kind"], string> = {
  OVERSPEED: "Excès de vitesse",
  RESTRICTED_ZONE_ENTRY: "Entrée en zone interdite",
  SITE_BOUNDARY_EXIT: "Sortie de la limite du site",
  SIGNAL_LOST: "Perte de signal",
};

function detail(a: Alert, tz: string): string {
  if (a.kind === "SIGNAL_LOST") return `Dernière position mesurée ${formatDateTime(a.last_measured_at, tz)}`;
  if (a.kind === "OVERSPEED") return `${a.peak_speed_kmh?.toFixed(1)} km/h au maximum pour ${a.speed_limit_kmh} km/h autorisés`;
  return a.geofence_name ?? "Zone";
}

/** Réglages du site : sans limite ni délai, aucune alerte de vitesse ni de perte de signal n'est produite. */
function SitePolicy({ siteId }: { siteId: string }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const managing = can(me.grants, "fleet.gps_policy.manage", siteId);
  const [value, setValue] = useState<string | null>(null);
  const [delay, setDelay] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const policy = useQuery({ queryKey: ["gps-policy", siteId], queryFn: () => get<Policy>(`/sites/${siteId}/gps-policy`) });
  const current = policy.data?.speed_limit_kmh ?? null;
  const currentDelay = policy.data?.signal_loss_minutes ?? null;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const limit = value ?? (current == null ? "" : String(current));
      const minutes = delay ?? (currentDelay == null ? "" : String(currentDelay));
      await request(`/sites/${siteId}/gps-policy`, {
        method: "PUT",
        body: { speed_limit_kmh: limit ? limit : null, signal_loss_minutes: minutes ? Number(minutes) : null },
      });
      setValue(null);
      setDelay(null);
      await queryClient.invalidateQueries({ queryKey: ["gps-policy", siteId] });
    } catch (failure) {
      setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card" aria-label="Réglages d'alerte du site">
      <h2>Réglages d'alerte du site</h2>
      <DataState loading={policy.isLoading} error={policy.error} empty={false}>
        <p>
          {current == null
            ? "Aucune limite : aucune alerte d'excès de vitesse n'est produite sur ce site."
            : `Alerte au-delà de ${current} km/h mesurés.`}{" "}
          {currentDelay == null
            ? "Perte de signal non surveillée."
            : `Perte de signal signalée après ${currentDelay} min sans position (engins disponibles équipés d'un traceur).`}
        </p>
        {managing && (
          <form onSubmit={(e) => void save(e)} className="inline-form">
            <label>
              Nouvelle limite (km/h, vide = aucune)
              <input type="number" min="1" max="250" step="0.1" value={value ?? (current == null ? "" : String(current))} onChange={(e) => setValue(e.target.value)} />
            </label>
            <label>
              Perte de signal après (min, vide = non surveillée)
              <input type="number" min="5" max="1440" step="1" value={delay ?? (currentDelay == null ? "" : String(currentDelay))} onChange={(e) => setDelay(e.target.value)} />
            </label>
            <button type="submit" disabled={saving}>Enregistrer</button>
          </form>
        )}
        {error != null && <ErrorMessage error={error} />}
      </DataState>
    </section>
  );
}

type Notification = Schemas["AlertNotificationOut"];

/** Choix personnel du canal de notification : e-mail, SMS, les deux, ou aucun (défaut). */
function MyNotifications() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["alert-notifications"], queryFn: () => get<Notification>("/me/alert-notifications") });
  const [draft, setDraft] = useState<{ email: boolean; sms: boolean; phone: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const data = prefs.data;
  const form = draft ?? { email: data?.email_enabled ?? false, sms: data?.sms_enabled ?? false, phone: data?.phone_e164 ?? "" };

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await request("/me/alert-notifications", {
        method: "PUT",
        body: { email_enabled: form.email, sms_enabled: form.sms, phone_e164: form.phone.trim() || null },
      });
      setDraft(null);
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["alert-notifications"] });
    } catch (failure) {
      setError(failure);
    }
  }

  return (
    <section className="card" aria-label="Mes notifications d'alertes">
      <h2>Mes notifications</h2>
      <p className="muted small">
        Recevoir les nouvelles alertes de vos sites. Au plus une notification par engin et par type d'alerte toutes les
        30 minutes. Aucune coordonnée n'est envoyée.
      </p>
      <DataState loading={prefs.isLoading} error={prefs.error} empty={false}>
        <form onSubmit={(e) => void save(e)} className="inline-form">
          <label className="checkbox">
            <input type="checkbox" checked={form.email} onChange={(e) => setDraft({ ...form, email: e.target.checked })} />
            Par e-mail
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={form.sms} onChange={(e) => setDraft({ ...form, sms: e.target.checked })} />
            Par SMS
          </label>
          <label>
            Numéro de mobile (format international, ex. +224…)
            <input type="tel" inputMode="tel" autoComplete="tel" pattern="\+[1-9][0-9]{7,14}" required={form.sms} value={form.phone} onChange={(e) => setDraft({ ...form, phone: e.target.value })} />
          </label>
          <button type="submit">Enregistrer mes choix</button>
        </form>
        {data && !data.sms_available && (
          <p className="warn-text small">Envoi de SMS pas encore disponible sur ce serveur (fournisseur non configuré) : vos choix sont enregistrés.</p>
        )}
        {saved && <p role="status">Choix enregistrés.</p>}
        {error != null && <ErrorMessage error={error} />}
      </DataState>
    </section>
  );
}

export function GpsAlertsPage() {
  const me = useMe();
  const { siteId, timezoneOf } = useSites();
  const queryClient = useQueryClient();
  const [pendingOnly, setPendingOnly] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const allowed = can(me.grants, "fleet.gps_alert.read", siteId);
  const managing = can(me.grants, "fleet.gps_alert.manage", siteId);
  const alerts = useQuery({
    queryKey: ["gps-alerts", siteId, pendingOnly],
    queryFn: () => get<{ items: Alert[]; total: number }>("/gps/alerts", { site_id: siteId, unacknowledged: pendingOnly, page_size: 100 }),
    enabled: allowed,
    refetchInterval: 30_000,
  });
  if (!allowed) return <AccessDenied />;

  async function acknowledge(id: string) {
    const note = window.prompt("Remarque (facultative) : action menée, conducteur prévenu…") ?? null;
    setBusy(id);
    setError(null);
    try {
      await request(`/gps/alerts/${id}/acknowledge`, { method: "POST", body: { note: note?.trim() || null } });
      await queryClient.invalidateQueries({ queryKey: ["gps-alerts"] });
      await queryClient.invalidateQueries({ queryKey: ["todo"] });
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Alertes GPS</h1>
          <p className="muted">
            Produites à partir des positions mesurées : excès de vitesse, entrée en zone interdite, sortie de la limite du
            site, perte de signal. Une position reçue en retard ne crée pas d'alerte.
          </p>
        </div>
      </div>
      <MyNotifications />
      {siteId && <SitePolicy siteId={siteId} />}
      <div className="card">
        <label className="checkbox">
          <input type="checkbox" checked={pendingOnly} onChange={(e) => setPendingOnly(e.target.checked)} />
          Seulement les alertes non prises en compte
        </label>
        {error != null && <ErrorMessage error={error} />}
        <DataState loading={alerts.isLoading} error={alerts.error} empty={!alerts.data?.items.length} emptyText="Aucune alerte.">
          <table>
            <thead>
              <tr>
                <th scope="col">Engin</th>
                <th scope="col">Alerte</th>
                <th scope="col">Détail</th>
                <th scope="col">Début (site)</th>
                <th scope="col">Fin</th>
                <th scope="col">Prise en compte</th>
              </tr>
            </thead>
            <tbody>
              {(alerts.data?.items ?? []).map((a) => {
                const tz = timezoneOf(a.site_id);
                return (
                  <tr key={a.gps_alert_id}>
                    <td>
                      <Link to={`/vehicules/${a.vehicle_id}`}>{a.fleet_number}</Link>
                    </td>
                    <td>{ALERT_KIND[a.kind]}</td>
                    <td>{detail(a, tz)}</td>
                    <td>{formatDateTime(a.opened_at, tz)}</td>
                    <td>{a.closed_at == null ? <strong>En cours</strong> : a.closed_at === a.opened_at ? "—" : formatDateTime(a.closed_at, tz)}</td>
                    <td>
                      {a.acknowledged_at ? (
                        <span>
                          {formatDateTime(a.acknowledged_at, tz)}
                          {a.acknowledgement_note ? ` — ${a.acknowledgement_note}` : ""}
                        </span>
                      ) : managing ? (
                        <button type="button" disabled={busy !== null} onClick={() => void acknowledge(a.gps_alert_id)}>
                          {busy === a.gps_alert_id ? "Enregistrement…" : "Prendre en compte"}
                        </button>
                      ) : (
                        "À prendre en compte"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DataState>
      </div>
    </section>
  );
}
