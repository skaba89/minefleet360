/** Enregistre le cache du shell statique. Les réponses API ne sont jamais mises en cache. */
export function registerOfflineShell(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return Promise.resolve(null);
  return navigator.serviceWorker.register("/sw.js", { scope: "/" });
}
