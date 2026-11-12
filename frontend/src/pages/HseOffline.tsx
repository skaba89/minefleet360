import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { Badge, ErrorMessage } from "../components/common";
import { ActionForm, Options, orNull } from "../components/forms";
import { accountOf, queueIncident, syncAccount, type Account, type IncidentDraft } from "../lib/hseOfflineSync";
import { HSE_CATEGORY, HSE_SEVERITY, label } from "../lib/labels";
import { listForAccount, removeEntry, type OutboxEntry } from "../lib/offline-outbox";
import { useConnectivity } from "../lib/connectivity";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";

export interface DeclarationSite {
  site_id: string;
  code: string;
  name: string;
}

const SYNC_INTERVAL_MS = 30_000;
/** Après un échec transitoire (réseau instable, réponse perdue), nouvelle tentative rapide au lieu d'attendre la cadence. */
const RETRY_FAST_MS = 5_000;

const REJECTION_TEXT: Record<string, string> = {
  PERMISSION_DENIED: "Vous n'avez plus le droit de déclarer sur ce site.",
  forbidden: "Vous n'avez plus le droit de déclarer sur ce site.",
  REFERENCE_NOT_FOUND: "Site ou engin introuvable ou hors de votre périmètre.",
  NOT_FOUND: "Site introuvable ou hors de votre périmètre.",
  VALIDATION_ERROR: "Déclaration refusée : données invalides.",
  IDEMPOTENCY_KEY_REUSED: "Conflit : cette opération a déjà été utilisée pour une autre déclaration.",
  CONFLICT: "Conflit avec l'état du serveur.",
};

/** Champs d'une déclaration, utilisables avec ou sans réseau (aucune donnée chargée à la demande). */
export function IncidentFields({
  form,
  set,
  sites,
}: {
  form: IncidentForm;
  set: (patch: Partial<IncidentForm>) => void;
  sites: DeclarationSite[];
}) {
  return (
    <>
      <label>
        Site
        <select required value={form.site_id} onChange={(e) => set({ site_id: e.target.value, vehicle_id: "" })}>
          <option value="">— Choisir —</option>
          {sites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Nature
        <select value={form.category} onChange={(e) => set({ category: e.target.value })}>
          <Options map={HSE_CATEGORY} />
        </select>
      </label>
      <label>
        Gravité estimée
        <select value={form.severity} onChange={(e) => set({ severity: e.target.value })}>
          <Options map={HSE_SEVERITY} />
        </select>
      </label>
      <label>
        Survenu le (heure du site)
        <input type="datetime-local" required value={form.occurred_at} onChange={(e) => set({ occurred_at: e.target.value })} />
      </label>
      <label>
        Titre
        <input required minLength={3} maxLength={200} value={form.title} onChange={(e) => set({ title: e.target.value })} />
      </label>
      <label>
        Description des faits
        <textarea required minLength={10} maxLength={4000} value={form.description} onChange={(e) => set({ description: e.target.value })} />
      </label>
      <label>
        Lieu (facultatif)
        <input maxLength={200} value={form.location_note} onChange={(e) => set({ location_note: e.target.value })} />
      </label>
      <label>
        Nombre de blessés
        <input type="number" min={0} max={500} value={form.injured_count} onChange={(e) => set({ injured_count: e.target.value })} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={form.lost_time} onChange={(e) => set({ lost_time: e.target.checked })} />
        Arrêt de travail
      </label>
      <label>
        Mesures immédiates prises (facultatif)
        <textarea maxLength={2000} value={form.immediate_actions} onChange={(e) => set({ immediate_actions: e.target.value })} />
      </label>
      <p className="muted small">Décrivez les faits sans nom de victime ni information médicale.</p>
    </>
  );
}

export interface IncidentForm {
  site_id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  occurred_at: string;
  location_note: string;
  vehicle_id: string;
  injured_count: string;
  lost_time: boolean;
  immediate_actions: string;
}

export function emptyIncidentForm(siteId: string, timeZone: string): IncidentForm {
  return {
    site_id: siteId,
    category: "NEAR_MISS",
    severity: "LOW",
    title: "",
    description: "",
    occurred_at: utcToZonedInput(new Date(), timeZone),
    location_note: "",
    vehicle_id: "",
    injured_count: "0",
    lost_time: false,
    immediate_actions: "",
  };
}

export function incidentBody(form: IncidentForm, timeZone: string): IncidentDraft {
  return {
    site_id: form.site_id,
    category: form.category as IncidentDraft["category"],
    severity: form.severity as IncidentDraft["severity"],
    title: form.title.trim(),
    description: form.description.trim(),
    occurred_at: zonedInputToUtc(form.occurred_at, timeZone).toISOString(),
    location_note: orNull(form.location_note),
    vehicle_id: form.vehicle_id || null,
    injured_count: Number(form.injured_count) || 0,
    lost_time: form.lost_time,
    immediate_actions: orNull(form.immediate_actions),
  };
}

function statusBadge(entry: OutboxEntry) {
  switch (entry.status) {
    case "synchronized":
      return <Badge tone="ok">Synchronisé — {entry.serverReference}</Badge>;
    case "rejected":
      return <Badge tone="bad">Refusé par le serveur</Badge>;
    case "syncing":
      return <Badge tone="warn">Synchronisation…</Badge>;
    default:
      return <Badge tone="warn">{entry.errorCode === "SESSION_EXPIRED" ? "En attente — reconnectez-vous" : "En attente de synchronisation"}</Badge>;
  }
}

/**
 * File des déclarations saisies sur cet appareil : état, accusé de réception serveur, rejets. Synchronise au
 * retour du réseau, périodiquement et à la demande, uniquement avec une session valide (`canSync`).
 */
export function OfflineIncidentQueue({
  account,
  canSync,
  canOpen,
  timeZone,
  refreshKey = 0,
  onSynchronized,
}: {
  account: Account;
  canSync: boolean;
  canOpen: boolean;
  timeZone: string;
  refreshKey?: number;
  onSynchronized?: () => void;
}) {
  const online = useConnectivity();
  const [entries, setEntries] = useState<OutboxEntry[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const running = useRef(false);
  const lastAttemptFailed = useRef(false);
  const notify = useRef(onSynchronized);
  notify.current = onSynchronized;
  const { tenantId, userId } = account;

  const reload = useCallback(async () => {
    try {
      const list = await listForAccount({ tenantId, userId });
      setEntries(list);
      // Une opération encore en attente (échec transitoire, backoff serveur court) demande un rejeu rapide.
      lastAttemptFailed.current = list.some((e) => e.status === "pending" || e.status === "syncing");
    } catch (err) {
      // Navigateur sans IndexedDB : pas de file locale à afficher (la saisie hors ligne y sera refusée).
      if (typeof indexedDB === "undefined") setEntries([]);
      else setError(err);
    }
  }, [tenantId, userId]);

  const sync = useCallback(async () => {
    if (running.current || !canSync) return;
    running.current = true;
    setError(null);
    try {
      const result = await syncAccount({ tenantId, userId });
      if (result.kind === "reauthenticate") setMessage("Session expirée : reconnectez-vous pour synchroniser.");
      else if (result.kind === "locked") setMessage("Synchronisation déjà en cours dans un autre onglet.");
      else {
        setMessage(null);
        if (result.synchronized > 0) notify.current?.();
      }
    } catch (err) {
      setError(err);
    } finally {
      running.current = false;
      await reload();
    }
  }, [tenantId, userId, canSync, reload]);

  useEffect(() => {
    void reload();
  }, [reload, refreshKey]);

  const pending = entries.some((e) => e.status === "pending" || e.status === "syncing");
  useEffect(() => {
    if (!online || !canSync || !pending) return;
    void sync();
    // Cadence normale de 30 s ; après une tentative en échec (backoff interne court), rejeu à 5 s pour
    // que l'accusé de réception arrive sans que l'agent de terrain attende une demi-minute en le regardant.
    let timer = 0;
    const schedule = () => {
      timer = window.setTimeout(() => {
        void sync();
        schedule();
      }, lastAttemptFailed.current ? RETRY_FAST_MS : SYNC_INTERVAL_MS);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [online, canSync, pending, sync]);

  if (entries.length === 0 && !error) return null;
  return (
    <section aria-label="Déclarations saisies sur cet appareil" className="card">
      <h2>Déclarations saisies sur cet appareil</h2>
      {!online && <p className="muted">Hors ligne : les déclarations seront envoyées au retour du réseau.</p>}
      {message && <p className="warn-text" role="status">{message}</p>}
      {error !== null && <ErrorMessage error={error} />}
      <ul>
        {entries.map((e) => {
          const payload = e.payload as Partial<IncidentDraft>;
          return (
            <li key={e.operationId}>
              <strong>{payload.title}</strong> — {label(HSE_CATEGORY, payload.category)} — saisi le {formatDateTime(e.createdAt, timeZone)}{" "}
              {statusBadge(e)}
              {e.status === "synchronized" && e.serverId && canOpen && (
                <>
                  {" "}
                  <Link to={`/hse/${e.serverId}`}>Ouvrir</Link>
                </>
              )}
              {e.status === "rejected" && (
                <div className="error small">{REJECTION_TEXT[e.errorCode ?? ""] ?? `Refus définitif (${e.errorCode ?? "inconnu"}).`} Ressaisissez la déclaration si nécessaire.</div>
              )}
              {(e.status === "synchronized" || e.status === "rejected") && (
                <button
                  type="button"
                  onClick={() => {
                    removeEntry(account, e.operationId).then(reload, setError);
                  }}
                >
                  Retirer de la liste
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {pending && (
        <button type="button" disabled={!online || !canSync} onClick={() => void sync()}>
          Synchroniser maintenant
        </button>
      )}
    </section>
  );
}

/** Ouverture sans réseau avec un profil terrain mémorisé : déclaration HSE et file d'attente seulement. */
export function OfflineFieldPage() {
  const { fieldProfile, retrySession } = useAuth();
  const [declaring, setDeclaring] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  if (!fieldProfile) return null;
  const account = accountOf(fieldProfile);
  const tzOf = (siteId: string) => fieldProfile.sites.find((s) => s.site_id === siteId)?.timezone ?? fieldProfile.timezone;
  return (
    <main className="container">
      <h1>MINEFLEET 360 — mode hors ligne</h1>
      <p className="muted">
        Connecté en tant que {fieldProfile.display_name}. Sans réseau, seule la déclaration d'incident HSE est disponible ; rien
        n'est envoyé avant le retour du réseau et la reconnexion de votre compte.
      </p>
      <button type="button" onClick={() => void retrySession()}>
        Réessayer la connexion
      </button>
      {confirmation && <p role="status" className="warn-text">{confirmation}</p>}
      {declaring ? (
        <QueueIncidentForm
          account={account}
          sites={fieldProfile.sites}
          timeZoneOf={tzOf}
          onQueued={() => {
            setConfirmation("Déclaration enregistrée sur l'appareil — en attente de synchronisation.");
            setRefreshKey((k) => k + 1);
            setDeclaring(false);
          }}
        />
      ) : (
        <button type="button" className="primary" onClick={() => setDeclaring(true)}>
          Déclarer un autre incident
        </button>
      )}
      <OfflineIncidentQueue account={account} canSync={false} canOpen={false} timeZone={fieldProfile.timezone} refreshKey={refreshKey} />
    </main>
  );
}

function QueueIncidentForm({
  account,
  sites,
  timeZoneOf,
  onQueued,
}: {
  account: Account;
  sites: DeclarationSite[];
  timeZoneOf: (siteId: string) => string;
  onQueued: () => void;
}) {
  const first = sites[0]?.site_id ?? "";
  const [form, setForm] = useState(() => emptyIncidentForm(first, timeZoneOf(first)));
  return (
    <ActionForm
      title="Déclarer un incident (hors ligne)"
      submitLabel="Enregistrer sur l'appareil"
      onSubmit={async () => {
        await queueIncident(account, incidentBody(form, timeZoneOf(form.site_id)));
        onQueued();
      }}
    >
      <IncidentFields form={form} set={(patch) => setForm({ ...form, ...patch })} sites={sites} />
    </ActionForm>
  );
}
