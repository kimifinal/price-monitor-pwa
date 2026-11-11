/**
 * monitor.js — the single source of truth for "should we alert?".
 *
 * Every alert decision in the app flows through here. The UI only renders
 * what these return. Pure functions, no DOM, so unit tests are trivial and the
 * coverage gate has a real, meaningful surface to protect.
 */

/**
 * A watched item.
 * @typedef {'name': string, 'url'?: string, 'price': number, 'target': number,
 *          'currency'?: string, 'id'?: string, 'createdAt'?: number} Item
 */

/**
 * Decide whether an item should trigger a price-drop alert.
 * Alert when the current price is at or below the user's target.
 * @param {Item} item
 * @returns {boolean}
 */
export function shouldAlert(item) {
  if (item == null) return false
  const { price, target } = item
  if (typeof price !== 'number' || typeof target !== 'number') return false
  if (!Number.isFinite(price) || !Number.isFinite(target)) return false
  return price <= target
}

/**
 * Percentage the price has fallen relative to target (0..100).
 * Positive => below target (good, should alert); negative => above.
 * @param {Item} item
 * @returns {number}
 */
export function percentBelowTarget(item) {
  if (item == null || typeof item.price !== 'number' || typeof item.target !== 'number') {
    return 0
  }
  if (item.target === 0) return 0
  return ((item.target - item.price) / item.target) * 100
}

/**
 * Sort a list by how "hot" it is — items closest to / below their target first.
 * @param {Item[]} items
 * @returns {Item[]} new sorted array (does not mutate input)
 */
export function sortByUrgency(items) {
  if (!Array.isArray(items)) return []
  const sorted = [...items].sort((a, b) => percentBelowTarget(b) - percentBelowTarget(a))
  return sorted
}

/**
 * Build a human-readable alert message for an item.
 * @param {Item} item
 * @returns {string}
 */
export function alertMessage(item) {
  if (item == null) return ''
  const pct = Math.round(percentBelowTarget(item))
  const name = item.name || '未命名'
  if (pct >= 0) {
    return `${name} 跌破目標價 $${item.target.toFixed(2)}（${pct}% 低於目標）`
  }
  return `${name} 尚未到價，離目標還差 ${Math.abs(pct)}%`
}

/**
 * Filter a list to only the items that should alert.
 * @param {Item[]} items
 * @returns {Item[]}
 */
export function alertedItems(items) {
  if (!Array.isArray(items)) return []
  return items.filter((i) => shouldAlert(i))
}

/* ---------------------------------------------------------------------------
 * 歷史價格比價 — the verdict SSOT, mirrored from backend/models.py:price_verdict.
 * Keep the thresholds + branch order in lockstep with the Python side.
 * ------------------------------------------------------------------------- */

// Mirrors backend/models.py constants.
const GOOD_DEAL_DROP = 15 // >= 15% below the high => a genuinely good deal
const NEAR_HIGH_DROP = 5 // <= 5% below => basically at the high

/**
 * Turn a price-history metrics object into a "is it a good time to buy?" verdict.
 * Mirrors `price_verdict` in the backend — the two must agree.
 * @param {{points?: number, atAllTimeLow?: boolean, dropPctFromHigh?: number}} m
 * @returns {{verdict: string, label: string, dropPct: number}}
 */
export function priceVerdict(m) {
  if (!m || !m.points) return { verdict: 'unknown', label: '無歷史資料', dropPct: 0 }
  const drop = m.dropPctFromHigh ?? 0
  if (m.atAllTimeLow) return { verdict: 'all_time_low', label: '歷史最低 👍', dropPct: drop }
  if (drop >= GOOD_DEAL_DROP) {
    return { verdict: 'good_deal', label: `較近低點 ▼${Math.round(drop)}%`, dropPct: drop }
  }
  if (drop <= NEAR_HIGH_DROP) return { verdict: 'near_high', label: '接近高點', dropPct: drop }
  return { verdict: 'stable', label: '平穩', dropPct: drop }
}

export const PRICE_THRESHOLDS = { GOOD_DEAL_DROP, NEAR_HIGH_DROP }

/**
 * Build an SVG polyline `d` string from a price series — an offline sparkline.
 * Accepts either [number] or [{price}] (or a mix with junk filtered out).
 * Pure => trivially unit-testable and meaningful for the coverage gate.
 * @param {Array<number|{price:number}>} points
 * @param {number} [width=100]
 * @param {number} [height=28]
 * @returns {string} SVG path (or '' when there's nothing to draw)
 */
export function sparkPath(points, width = 100, height = 28, pad = 1) {
  if (!Array.isArray(points) || points.length === 0) return ''
  const vals = points
    .map((p) => (typeof p === 'number' ? p : p?.price))
    .filter((v) => typeof v === 'number' && Number.isFinite(v))
  if (vals.length === 0) return ''
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const step = width / (vals.length - 1 || 1)
  return vals
    .map((v, i) => {
      const x = i * step
      const y = pad + (1 - (v - min) / span) * (height - 2 * pad)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}
