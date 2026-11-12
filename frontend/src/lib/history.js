/**
 * history.js — turn a /api/costco/history or /api/crypto payload into the card
 * objects the 歷史價格比價 UI renders, with a FULLY-OFFLINE loader.
 *
 * Issue #6: the app must render its price-movement cards with no network. The
 * offline path is: try the live API (the service worker in src/sw.js serves the
 * cache, or the baked-in snapshot on a miss); if the live fetch fails outright,
 * read the committed snapshot JSON directly (it ships in the install bundle, so
 * it is available even on a never-online first load).
 *
 * The mapper `cardsFromHistory` is pure and is the single place that bridges the
 * backend's snake_case metrics to the camelCase `metrics` the card renderer
 * (PriceHistory.vue / monitor.js) consumes — so a Costco item and a CoinGecko
 * coin render identically (the multi-source SSOT from #3).
 */
import { SNAPSHOT_DIR, joinBase } from './offline-cache.js'

/** Committed baked-in snapshot, resolved relative to the app base. */
export const SNAPSHOT_PATHS = {
  costco: { live: 'api/costco/history', snapshot: joinBase(SNAPSHOT_DIR, 'costco-history.json') },
  crypto: { live: 'api/crypto', snapshot: joinBase(SNAPSHOT_DIR, 'crypto.json') },
}

/**
 * Map one backend item (snake_case metrics + verdict + optional `series`) to a
 * card the renderer can draw. Accepts both the list-item form (no `series`) and
 * the per-sku/coin form (carries `series` for the sparkline). Returns null for
 * junk so a bad item can't poison the list.
 */
export function mapItem(item, source) {
  if (!item || typeof item !== 'object') return null
  const series = (Array.isArray(item.series) ? item.series : [])
    .map((p) => (typeof p === 'number' ? p : p && typeof p.price === 'number' ? p.price : Number.NaN))
    .filter((v) => Number.isFinite(v))
  const dropPct =
    item.drop_pct_from_high != null
      ? item.drop_pct_from_high
      : item.dropPctFromHigh != null
        ? item.dropPctFromHigh
        : (item.verdict && item.verdict.dropPct) != null
          ? item.verdict.dropPct
          : 0
  const metrics = {
    points: item.points != null ? item.points : series.length,
    atAllTimeLow: item.at_all_time_low != null ? item.at_all_time_low : item.atAllTimeLow ?? false,
    dropPctFromHigh: dropPct,
  }
  const card = {
    name: item.name || item.sku || `#${item.sku}`,
    current: item.current,
    metrics,
    url: item.url,
    source: source || item.source || item.tag || 'costco',
    currency: item.currency || '',
    tag: item.tag,
  }
  if (series.length) card.series = series
  return card
}

/**
 * Map a payload — `/api/*` ({count, items: []}) or a bare item array — into
 * renderable cards. Source threads through so a coin keeps its 🪙 badge.
 * @returns {Array<object>} possibly empty
 */
export function cardsFromHistory(payload, source) {
  if (!payload || typeof payload !== 'object') return []
  const items = Array.isArray(payload) ? payload : payload.items
  if (!Array.isArray(items)) return []
  return items.map((it) => mapItem(it, source)).filter(Boolean)
}

function joinUrl(base, rel) {
  const b = base ? `${base}/` : ''
  return b + rel
}

/**
 * Load live history for the movement cards, degrading gracefully all the way to
 * the committed snapshot. NEVER throws — a total failure yields [] so the UI can
 * still render its hard-coded fallback samples. Each endpoint falls back to its
 * own baked snapshot so even a never-online load shows the last known series.
 *
 * @param {string} baseURL e.g. import.meta.env.BASE_URL
 * @param {object} [opts] { fetch?: typeof fetch }
 * @returns {Promise<Array<object>>}
 */
export async function loadLiveHistory(baseURL = '', opts = {}) {
  const fetch = opts.fetch || globalThis.fetch
  if (typeof fetch !== 'function') return []
  const [costco, crypto] = await Promise.all([
    tryEndpoint(SNAPSHOT_PATHS.costco, baseURL, 'costco', fetch),
    tryEndpoint(SNAPSHOT_PATHS.crypto, baseURL, 'coingecko', fetch),
  ])
  return [...costco, ...crypto]
}

async function tryEndpoint({ live, snapshot }, baseURL, source, fetch) {
  // 1) live API (served by the SW: fresh cache when online, snapshot when offline)
  try {
    const res = await fetch(joinUrl(baseURL, live), { cache: 'no-store' })
    if (res && res.ok) {
      const cards = cardsFromHistory(await res.json(), source)
      if (cards.length) return cards
    }
  } catch {
    /* offline / 404 — fall through to the baked snapshot */
  }
  // 2) baked-in snapshot (committed, always in the install bundle → offline-safe)
  try {
    const res = await fetch(joinUrl(baseURL, snapshot), { cache: 'no-store' })
    if (res && res.ok) return cardsFromHistory(await res.json(), source)
  } catch {
    /* nothing reachable — caller renders its hard-coded fallback samples */
  }
  return []
}
