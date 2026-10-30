import { useConnectivity } from "../lib/connectivity";

export function ConnectivityStatus() {
  const online = useConnectivity();
  return (
    <span
      className={`connectivity-status connectivity-status--${online ? "online" : "offline"}`}
      role="status"
      aria-live="polite"
      title={online ? "Connexion réseau disponible" : "Connexion réseau indisponible"}
    >
      <span className="connectivity-dot" aria-hidden="true" />
      {online ? "Connecté" : "Hors ligne"}
    </span>
  );
}

/** Avertissement global également visible avant la connexion. */
export function OfflineNotice() {
  const online = useConnectivity();
  if (online) return null;
  return (
    <aside className="offline-notice" role="alert">
      <strong>Mode hors ligne.</strong> Les écrans déjà chargés restent consultables tant que l’application reste
      ouverte. Les enregistrements et la synchronisation reprendront après le retour du réseau.
    </aside>
  );
}
