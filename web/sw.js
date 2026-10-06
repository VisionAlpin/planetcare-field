/* PlanetCare Field: Service Worker v0.6.0
   Seiten (HTML): zuerst Netz, offline aus dem Cache. Statische Dateien: Cache, im Hintergrund aktualisieren.
   API, Anmeldung und /health: nie aus dem Cache. Bei jedem Release CACHE erhöhen. */
const CACHE = "pcf-0.6.0";
const STATIC_ASSETS = [
  "/demo",
  "/login",
  "/styles/tokens.css", "/styles/overview.css", "/styles/measures.css", "/styles/market.css",
  "/js/icons.js", "/js/overview.js", "/js/measures.js", "/js/market.js", "/js/shell.js",
  "/manifest.json", "/favicon.ico", "/icons/logo-mark.svg"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/") || url.pathname === "/health") return; // Browser normal

  if (e.request.mode === "navigate") {
    // Seiten: Netz zuerst, damit Anmeldung und neue Versionen sofort greifen
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request).then((r) => r || caches.match("/demo"))));
    return;
  }
  // Statische Dateien: sofort aus dem Cache, parallel aktualisieren
  e.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(e.request).then((cached) => {
        const net = fetch(e.request).then((res) => { if (res.ok) cache.put(e.request, res.clone()); return res; }).catch(() => cached);
        return cached || net;
      })
    )
  );
});
