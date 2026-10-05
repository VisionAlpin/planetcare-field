/* PlanetCare Field — Service Worker v0.4.1 */
const CACHE = 'pcf-0.4.1';
const STATIC_ASSETS = [
  '/',
  '/demo',
  '/styles/tokens.css',
  '/styles/overview.css',
  '/js/icons.js',
  '/js/overview.js',
  '/manifest.json',
  '/favicon.ico',
];

// Install: statische Dateien cachen
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: alte Caches löschen
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: /api/ IMMER vom Netz, nie aus Cache
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API-Anfragen nie cachen
  if (url.pathname.startsWith('/api/') || url.pathname === '/health') {
    e.respondWith(fetch(e.request));
    return;
  }

  // Statische Dateien: Cache First, dann Netz
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
