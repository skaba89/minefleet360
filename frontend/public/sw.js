const CACHE_NAME = "minefleet-shell-v1";
const STATIC_FILES = [
  "/manifest.webmanifest",
  "/assets/minefleet-icon.svg",
  "/assets/mining-login.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    const indexResponse = await fetch("/index.html", { cache: "no-cache" });
    if (!indexResponse.ok) throw new Error("Le shell MINEFLEET est indisponible.");
    const html = await indexResponse.clone().text();
    const generatedAssets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((match) => match[1]);
    await cache.put("/index.html", indexResponse);
    await cache.addAll([...new Set([...STATIC_FILES, ...generatedAssets])]);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Les données authentifiées et les mutations restent exclusivement gérées par l'API.
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) caches.open(CACHE_NAME).then((cache) => cache.put("/index.html", response.clone()));
          return response;
        })
        .catch(() => caches.match("/index.html", { ignoreVary: true })),
    );
    return;
  }

  if (["script", "style", "image", "font"].includes(request.destination)) {
    event.respondWith(
      caches.match(request, { ignoreVary: true }).then((cached) => cached ?? fetch(request).then((response) => {
        if (response.ok) caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
        return response;
      })),
    );
  }
});
