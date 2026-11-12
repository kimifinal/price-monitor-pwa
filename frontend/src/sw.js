/* eslint-disable */
/**
 * Service worker for the Price Monitor PWA (issue #6: 離線 PWA).
 *
 * This file is a THIN adapter: all the offline behaviour lives in the pure,
 * unit-tested `src/lib/offline-cache.js` (`handleFetch`). Here we only plug the
 * real Web APIs (caches / fetch / navigator.onLine / the precache manifest that
 * vite-plugin-pwa injects as `self.__WB_MANIFEST`) into that module's env slots,
 * and manage install / activate. It is deliberately excluded from ESLint
 * (see eslint.config.js: 'src/sw.js' is ignored) — it is a build-time-only
 * bridge, not business logic.
 *
 * What it guarantees, offline:
 *   • /api/costco/history* resolves from the response cache,
 *     else the committed snapshot (public/snapshot/*.json, precached here) ->
 *     the 歷史價格比價 price-movement cards always have last-known series +
 *     verdicts even with no network.
 *   • the app shell (index.html + assets + manifest, precached by vite-plugin-
 *     pwa in SHELL_CACHE) loads from cache, so the whole page renders offline.
 */
import { handleFetch, CACHE_NAME, SHELL_CACHE, resolveUrl, SNAPSHOT_DIR } from './lib/offline-cache.js'

// The two committed snapshots are precached so even a never-online first load
// has the last known series to render the cards from.
const SNAPSHOT_FILES = ['costco-history.json']

// Install: precache the app shell (manifest injected by vite-plugin-pwa) and the
// committed snapshots. `cache.add` with no-cors tolerates a single 404/fail: we
// wrap each add so one missing asset can't block installation.
self.addEventListener('install', (event) => {
  const shell = (self.__WB_MANIFEST || []).map((e) => e.url || e).map((u) => resolveUrl(base(), u))
  const snaps = SNAPSHOT_FILES.map((f) => resolveUrl(base(), `${SNAPSHOT_DIR}/${f}`))
  event.waitUntil(
    Promise.all([
      precache(self, SHELL_CACHE, shell),
      precache(self, CACHE_NAME, snaps),
    ]),
  )
})

async function precache(selfRef, cacheName, urls) {
  const cache = await selfRef.caches.open(cacheName)
  await Promise.all(
    urls.map((u) =>
      cache
        .add(new Request(u, { mode: 'no-cors' }))
        .catch(() => /* a single uncached asset must not block installation */ {}),
    ),
  )
}

// Activate: drop any older cache names, then take control of all clients so the
// new handlers + snapshot take effect without a manual refresh.
self.addEventListener('activate', (event) => {
  const keep = new Set([CACHE_NAME, SHELL_CACHE])
  event.waitUntil(
    self.caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.has(k)).map((k) => self.caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

// Fetch: hand every request to the pure strategy with a real-Web-API env.
self.addEventListener('fetch', (event) => {
  const request = event.request
  // Let cross-origin asset loads and non-GET traffic fall straight through.
  if (request.method !== 'GET') return
  const env = {
    online: navigator.onLine,
    base: base(),
    indexUrl: new URL('index.html', base()).href,
    fetch: (r, init) => fetch(r, init),
    match: (name, key) => self.caches.open(name).then((c) => c.match(key)),
    put: (name, key, res) => self.caches.open(name).then((c) => c.put(key, res)),
  }
  event.respondWith(handleFetch(request, env).catch(() => (event.defaultAction || null)))
})

function base() {
  // The SW's own directory: '/sw.js' at root -> '/', '/repoA/sw.js' -> '/repoA/'.
  return new URL('.', self.location).href
}
