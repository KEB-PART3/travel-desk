// Travel Desk — offline shell.
// Cache tag is stamped by deploy.sh from a content hash — do not edit by hand.
const CACHE = '__CACHE_TAG__';

const ASSETS = [
  './',
  './index.html',
  './trips.json',
  './photos.js',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png',
  './apple-touch-icon.png',
  /*__IMG_ASSETS__*/ /* stamped by deploy.sh from dist/img/* — do not edit by hand */
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network-first for the page so a fresh itinerary wins when there is signal,
// falling back to cache the moment there isn't. Everything else is cache-first.
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Let the page's version probe reach the origin untouched, so a stale
  // page can always detect a newer build (see the __TD_BUILD check in index.html).
  if (url.pathname.endsWith('/sw.js')) return;

  const isPage = req.mode === 'navigate'
    || url.pathname.endsWith('/')
    || url.pathname.endsWith('index.html')
    || url.pathname.endsWith('trips.json');

  if (isPage) {
    event.respondWith(
      fetch(req)
        .then(res => {
          // Cache only a clean 200 served for this exact URL — never store
          // the login redirect or an error page under an itinerary URL.
          if (res.ok && new URL(res.url).pathname === url.pathname) {
            const copy = res.clone();
            caches.open(CACHE).then(c => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then(r => r || caches.match('./index.html')))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(hit => hit || fetch(req).then(res => {
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => hit))
  );
});
