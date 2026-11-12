// The OFFLINE GUARD for issue #6.
//
// The service-worker strategy in src/lib/offline-cache.js is pure (every side
// effect is injected), so we can prove the full offline contract in Node/jsdom
// WITHOUT a browser — the Playwright e2e can't run locally (browser download is
// blocked), so these unit tests ARE the guard that /api/costco/history + the
// baked-in snapshot render the 歷史價格比價 cards with no network.
import { beforeEach, describe, it, expect } from 'vitest'
import {
  handleFetch,
  isApiRequest,
  isNavigation,
  snapshotFileFor,
  resolveUrl,
  CACHE_NAME,
  SHELL_CACHE,
} from '../../src/lib/offline-cache.js'
// Tie the offline contract to the COMMITTED baked snapshot (the git-diffable SSOT):
// offline must be able to render a movement card out of exactly these files.
import costcoSnapshot from '../../public/snapshot/costco-history.json'
import { cardsFromHistory } from '../../src/lib/history.js'

/* --- in-memory fakes -------------------------------------------------------- */
class MCache {
  constructor(entries = []) {
    this.m = new Map()
    for (const [url, res] of entries) this.m.set(url, res.clone())
  }
  async match(key) {
    const r = this.m.get(urlOf(key))
    return r ? r.clone() : null
  }
  async put(key, res) {
    this.m.set(urlOf(key), res.clone())
  }
}
const urlOf = (k) => (typeof k === 'string' ? k : k.url)
const jsonRes = (obj, status = 200, type = 'application/json') =>
  new Response(JSON.stringify(obj), { status, headers: { 'content-type': type } })
// A cache + env wired for a given online flag + network behaviour.
function env({
  online = false,
  cacheEntries = {},
  network = () => Promise.resolve(jsonRes({ count: 0, items: [] })),
  indexUrl = 'http://localhost/index.html',
} = {}) {
  const caches = new Map()
  const ensure = (name) => {
    if (!caches.has(name)) caches.set(name, new MCache())
    return caches.get(name)
  }
  // Both strategy caches always exist; provided entries are merged in.
  for (const [name, entries] of Object.entries(cacheEntries)) {
    const c = ensure(name)
    for (const [url, res] of entries) c.m.set(url, res.clone())
  }
  ensure(CACHE_NAME)
  ensure(SHELL_CACHE)
  return {
    online,
    base: 'http://localhost/',
    indexUrl,
    fetch: async (req) => {
      const res = await network(typeof req === 'string' ? req : req.url)
      if (res && res.status >= 500) throw new Error('network down')
      return res
    },
    match: async (name, key) => {
      const c = caches.get(name)
      return c ? c.match(key) : null
    },
    put: async (name, key, res) => {
      const c = caches.get(name)
      if (c) await c.put(key, res)
    },
  }
}

beforeEach(() => {})

describe('offline-cache matchers', () => {
  it('recognizes the API endpoints the cards fetch', () => {
    expect(isApiRequest('/api/costco/history')).toBe(true)
    expect(isApiRequest('/api/costco/history/149699')).toBe(true)
    expect(isApiRequest(new Request('http://h/api/costco/history'))).toBe(true)
    expect(isApiRequest('/api/items')).toBe(false)
    expect(isApiRequest('/')).toBe(false)
  })

  it('maps each endpoint to its committed snapshot file', () => {
    expect(snapshotFileFor('/api/costco/history')).toBe('snapshot/costco-history.json')
    expect(snapshotFileFor('/api/costco/history/1')).toBe('snapshot/costco-history.json')
    expect(snapshotFileFor('/api/items')).toBe(null)
  })

  it('distinguishes navigations from data requests', () => {
    // Browsers set request.mode='navigate' for document requests; undici's
    // Request can't be constructed with that mode in Node, so simulate with a
    // shape the strategy only reads `.url` + `.mode` from.
    expect(isNavigation({ url: 'http://h/', mode: 'navigate' })).toBe(true)
    expect(isNavigation(new Request('http://h/api/costco/history'))).toBe(false)
    expect(isNavigation('a string')).toBe(false)
    expect(isNavigation(null)).toBe(false)
  })

  it('resolves relative asset URLs against a base, tolerantly', () => {
    expect(resolveUrl('http://h/', 'snapshot/x.json')).toBe('http://h/snapshot/x.json')
    expect(resolveUrl('http://h/sub/', 'snapshot/x.json')).toBe('http://h/sub/snapshot/x.json')
    expect(resolveUrl('not a url', 'a/b')).toBe('a/b') // bad base -> raw rel
  })
})

describe('offline data contract — /api/costco/history', () => {
  it('OFFLINE + cache hit: serves the cached series verbatim', async () => {
    const e = env({
      online: false,
      cacheEntries: { [CACHE_NAME]: [['http://localhost/api/costco/history', jsonRes(costcoSnapshot)]] },
      network: () => { throw new Error('no network in offline mode') },
    })
    const res = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect(res).not.toBe(null)
    expect(res.status).toBe(200)
    const cards = cardsFromHistory(await res.json(), 'costco')
    expect(cards.length).toBeGreaterThan(0)
    // the "movement card" proof: an online-offline series with a verdict
    expect(cards.some((c) => c.series && c.series.length > 1)).toBe(true)
  })

  it('OFFLINE + cache miss: falls back to the baked-in snapshot', async () => {
    // No live entry, but the precached snapshot for this endpoint IS present
    const e = env({
      online: false,
      cacheEntries: {
        [CACHE_NAME]: [['http://localhost/snapshot/costco-history.json', jsonRes(costcoSnapshot)]],
      },
      network: () => { throw new Error('no network in offline mode') },
    })
    const res = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect(res).not.toBe(null)
    // the snapshot must be enough to render a movement card — exactly #6's goal
    const cards = cardsFromHistory(await res.json(), 'costco')
    expect(cards.length).toBeGreaterThan(0)
    expect(cards.every((c) => c.metrics)).toBe(true)
    // the snapshot was also persisted under the API key (next read is cache-first)
    const again = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect((await again.json()).count).toBeGreaterThan(0)
  })

  it('OFFLINE + nothing cached: onNotFound yields null (no throw)', async () => {
    const e = env({ online: false, cacheEntries: {} })
    const res = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect(res).toBeNull()
  })
})

describe('online refresh — stale-while-revalidate', () => {
  it('OFFLINE-cold: a successful 2xx network response is served AND cached', async () => {
    const e = env({
      online: true,
      network: (u) => u.includes('/api/costco/history') ? Promise.resolve(jsonRes(costcoSnapshot)) : Promise.resolve(jsonRes({})),
    })
    const first = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect((await first.json()).count).toBeGreaterThan(0)
    // now it is cached — a subsequent OFFLINE read hits the cache
    const off = env({
      online: false,
      cacheEntries: { [CACHE_NAME]: await readCache(e) },
      network: () => { throw new Error('offline') },
    })
    const cached = await handleFetch(new Request('http://localhost/api/costco/history'), off)
    expect((await cached.json()).count).toBeGreaterThan(0)
  })

  it('serves the stale cache instantly and refreshes it in the background', async () => {
    const e = env({
      online: true,
      cacheEntries: { [CACHE_NAME]: [['http://localhost/api/costco/history', jsonRes({ count: 1, items: [] })]] },
      network: (u) => (u.includes('/api/costco/history') ? Promise.resolve(jsonRes({ count: 99, items: [] })) : Promise.resolve(jsonRes({}))),
    })
    // stale-while-revalidate: the OLD value is handed back immediately...
    const res = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect((await res.json()).count).toBe(1)
    // ...and the background refresh has now overwritten the cache with the new one
    await flush()
    const again = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect((await again.json()).count).toBe(99)
  })

  it('network failure with an empty cache degrades to the snapshot', async () => {
    const e = env({
      online: true,
      cacheEntries: {
        [CACHE_NAME]: [['http://localhost/snapshot/costco-history.json', jsonRes(costcoSnapshot)]],
      },
      network: () => Promise.resolve(jsonRes({}, 503)), // 5xx -> treated as a failed fetch
    })
    const res = await handleFetch(new Request('http://localhost/api/costco/history'), e)
    expect((await res.json()).count).toBeGreaterThan(0)
  })
})

describe('navigations + passthrough', () => {
  it('OFFLINE navigation: falls back to the cached index shell', async () => {
    const e = env({
      online: false,
      indexUrl: 'http://localhost/index.html',
      cacheEntries: { [SHELL_CACHE]: [['http://localhost/index.html', new Response('<html></html>', { status: 200 })]] },
      network: () => { throw new Error('offline') },
    })
    const res = await handleFetch({ url: 'http://localhost/', mode: 'navigate' }, e)
    expect(res.status).toBe(200)
    expect(await res.text()).toContain('<html>')
  })

  it('non-API, non-nav request passes straight through to the network online', async () => {
    const e = env({ online: true, network: () => Promise.resolve(new Response('asset', { status: 200 })) })
    const res = await handleFetch(new Request('http://localhost/assets/app.js'), e)
    expect(await res.text()).toBe('asset')
  })
})

/* --- test helpers ----------------------------------------------------------- */
async function readCache(e) {
  // expose the MCache entries back out for seeding a second (offline) env
  const snapshot = []
  // MCache stores by url; we re-pull via a round-trip match against a wildcard
  const urls = ['http://localhost/api/costco/history']
  for (const u of urls) {
    const r = await e.match(CACHE_NAME, new Request(u))
    if (r) snapshot.push([u, r])
  }
  return snapshot
}
// Flush microtasks so the fire-and-forget background refresh completes.
async function flush() {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}
