/**
 * offline-cache.js — pure, side-effect-free service-worker fetch strategy.
 *
 * Issue #6 (部署收尾 / 離線 PWA): the whole app — incl. the 歷史價格比價
 * price-movement cards — must work FULLY OFFLINE. This is the deterministic,
 * testable heart of that guarantee. It imports NO web globals (`caches`/`self`/
 * `fetch` live only in `src/sw.js`): every side effect arrives through an
 * injected `env`, so the strategy is unit-tested in Node/jsdom with in-memory
 * fakes. `src/sw.js` is a 20-line wire that plugs real Web APIs into these
 * slots — the logic that a CI browser test would otherwise have to run.
 *
 * Strategy (the "safe subset" of #6 — no account config, no secret):
 *   /api/costco/history*, /api/crypto* (offline data the cards need):
 *       online  -> stale-while-revalidate: serve the cache NOW and refresh the
 *                  cache in the background; if the network FAILS, fall back to
 *                  the baked-in snapshot (last known series + verdicts).
 *       offline -> cache-first; on a cache miss, serve the baked-in snapshot.
 *   navigations -> network-first, fall back to the cached index.html shell.
 *   everything else -> pass straight through to the network.
 *
 * The baked-in snapshot is committed JSON (public/snapshot/*.json, the git-
 * diffable SSOT) that is PRECACHED at install time, so even a never-online
 * first load can render the last known series offline.
 */

// Cache names. Bumping the version on a schema change gives a clean cutover
// (old caches are garbage-collected by the activation handler in src/sw.js).
export const CACHE_NAME = 'price-monitor-data-v1'
export const SHELL_CACHE = 'price-monitor-shell-v1'
export const SNAPSHOT_DIR = 'snapshot'

// Which committed snapshot stands in for which endpoint when both the network
// and the response cache miss. The path prefix is enough — a per-sku request
// (/api/costco/history/123) still falls back to the whole costco snapshot.
export function snapshotFileFor(path) {
  if (/^\/api\/costco\/history/.test(path)) return joinBase(SNAPSHOT_DIR, 'costco-history.json')
  if (/^\/api\/crypto/.test(path)) return joinBase(SNAPSHOT_DIR, 'crypto.json')
  return null
}

export function joinBase(dir, file) {
  return `${dir}/${file}`
}

/**
 * Resolve a relative asset URL against a base. Pure + tolerant: a bad base
 * returns the raw relative path rather than throwing (the SW is the one place
 * this must never throw).
 */
export function resolveUrl(base, rel) {
  try {
    return new URL(rel, base).toString()
  } catch {
    return rel
  }
}

function urlPath(input) {
  if (input == null) return ''
  const raw = typeof input === 'string' ? input : input.url || ''
  if (!raw) return ''
  if (raw.startsWith('/')) return raw.split('?')[0]
  try {
    return new URL(raw).pathname
  } catch {
    return ''
  }
}

/** True for the API endpoints the cards fetch (/api/costco/history*, /api/crypto*). */
export function isApiRequest(input) {
  return /^\/api\/(costco\/history|crypto)\b/.test(urlPath(input))
}

/** True for a document navigation (deep link / reload). */
export function isNavigation(input) {
  return !!(input && typeof input === 'object' && input.mode === 'navigate')
}

/* -------------------------------------------------------------------------- */
/* Core routing                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Route one request through the offline strategy.
 *
 * @param {Request|string} request
 * @param {object} env injected environment:
 *   - online      boolean (default true) — is the network available?
 *   - base        string — base URL to resolve the snapshot dir against
 *   - indexUrl    string — cached shell to serve on a navigation miss
 *   - fetch       (request) => Promise<Response> — the real network (throws offline)
 *   - match       (cacheName, request) => Promise<Response|null>
 *   - put         (cacheName, request, response) => Promise<void> (must clone)
 *   - snapshotFile string|null — override for the snapshot path of this request
 *   - snapshot    Response|null — an already-baked snapshot Response (test hook)
 *   - cacheKey    (request) => Request — how to key the cache (default: same url)
 *   - onNotFound  (request) => Response|null — last-resort when nothing is cached
 * @returns {Promise<Response|null>}
 */
export async function handleFetch(request, env = {}) {
  const e = normalizeEnv(env)
  const path = urlPath(request)
  if (isApiRequest(path)) return apiStrategy(request, path, e)
  if (isNavigation(request)) return navigationStrategy(request, e)
  return passthroughStrategy(request, e)
}

function normalizeEnv(env) {
  return {
    online: env.online !== false,
    base: env.base || 'http://localhost/',
    indexUrl: env.indexUrl || '/',
    fetch: env.fetch || (() => {
      throw new Error('env.fetch is required (no network available in this unit test)')
    }),
    match: env.match || (() => Promise.resolve(null)),
    put: env.put || (() => {}),
    cacheKey: env.cacheKey,
    snapshot: env.snapshot == null ? null : env.snapshot,
    snapshotFile: env.snapshotFile == null ? undefined : env.snapshotFile,
    onNotFound: env.onNotFound || (() => null),
  }
}

async function apiStrategy(request, path, e) {
  // Normalize to a Request so the key, the network call, and the onNotFound hook
  // all see the same thing — callers may pass a string URL or a Request.
  const url = typeof request === 'string' ? resolveUrl(e.base, request) : request.url
  const req = typeof request === 'string' ? new Request(url) : request
  const key = e.cacheKey ? e.cacheKey(new Request(url)) : new Request(url)

  let cached = await e.match(CACHE_NAME, key)

  if (e.online) {
    // Stale-while-revalidate: hand back the cache immediately and refresh it in
    // the background so the UI never waits AND the cache stays fresh for next
    // time (incl. the next offline session).
    if (cached) {
      void backgroundRefresh(req, key, e).catch(() => {})
      return cached
    }
    // Cold cache: wait for the network, but a network failure must NOT break the
    // offline contract — degrade to the baked-in snapshot instead.
    try {
      const net = await e.fetch(req)
      if (net && net.ok) {
        await e.put(CACHE_NAME, key, net.clone())
        return net
      }
    } catch {
      /* network threw (e.g. 0 / TypeError) — fall through to snapshot */
    }
    return await snapshotFor(request, path, key, e)
  }

  // Offline: serve the cache; on a miss use the baked-in snapshot.
  if (cached) return cached
  return await snapshotFor(request, path, key, e)
}

async function backgroundRefresh(req, key, e) {
  const net = await e.fetch(req)
  if (net && net.ok) await e.put(CACHE_NAME, key, net.clone())
}

/**
 * Last resort for an API miss: the committed snapshot JSON. Returns a FRESH
 * clone so the caller can consume it without draining the cached copy.
 */
async function snapshotFor(request, path, key, e) {
  let snap = null
  // (1) an explicitly injected snapshot Response (test / single-source bake)
  if (e.snapshot) snap = e.snapshot
  // (2) the precached baked-in snapshot for this endpoint
  if (!snap) {
    const file = e.snapshotFile !== undefined ? e.snapshotFile : snapshotFileFor(path)
    if (file) {
      const req = new Request(resolveUrl(e.base, file))
      snap = await e.match(CACHE_NAME, req)
      if (!snap) snap = await e.match(SHELL_CACHE, req)
    }
  }
  if (!snap) return e.onNotFound(request)
  // Persist under the API key so the next read is cache-first (true stale-first).
  await e.put(CACHE_NAME, key, snap.clone())
  return snap.clone()
}

async function navigationStrategy(request, e) {
  if (e.online) {
    try {
      const net = await e.fetch(request)
      await e.put(SHELL_CACHE, new Request(e.indexUrl), net.clone())
      return net
    } catch {
      /* offline navigation -> cached shell */
    }
  }
  const shell = await e.match(SHELL_CACHE, new Request(e.indexUrl))
  return shell || null
}

async function passthroughStrategy(request, e) {
  return e.fetch(request)
}
