/**
 * newarrivals.js — the \"新品\" (new-arrivals) tab's offline data layer.
 *
 * Issue #48: the mobile app gains a discovery-oriented 新品 tab that filters the
 * baked costco-history snapshot by how recently each item first appeared
 * (`first_seen`), by 時段 (近 7/14/30 天 / 全部), and by 類別 (the `tag`
 * field). Everything is fully OFFLINE: the snapshot is a build-time import
* (the SAME pattern as catalog.js / mvm.js / history.js), so the tab renders
* with zero network.
*
* Pure + null-safe (gate 19): every exported function accepts junk input and
* returns a sensible empty/neutral result rather than throwing — a missing or
* unparseable `first_seen` never crashes a filter.
 */
import costcoHistoryData from '../data/costco-history.json'
import { formatTWD } from './format.js'

/**
 * The full new-arrivals dataset (build-time import, like mvm.js / history.js),
 * resolved to a plain array so callers can pass their own list to the helpers
* in tests. Null-safe: a non-array snapshot yields [].
 */
export const allItems = Array.isArray(costcoHistoryData?.items)
  ? costcoHistoryData.items
  : []

/**
 * Milliseconds of an ISO timestamp, or NaN when the value is missing/unparseable.
* Null-safe — never throws.
* @param {string} iso
* returns {number} epoch ms, or NaN
 */
function ts(iso) {
  if (iso == null) return NaN
  const t = Date.parse(iso)
  return Number.isFinite(t) ? t : NaN
}

/**
 * Converts a Date or string to a Date object.
* @param {Date|string} d
* returns {Date}
 */
function toDate(d) {
  if (d == null) return new Date()
  if (d instanceof Date) return d
  const t = Date.parse(d)
  return Number.isFinite(t) ? new Date(t) : new Date()
}

/**
 * Whole days between an ISO `first_seen` and `refDate` (refDate - first_seen),
* floored toward zero. A missing/unparseable `first_seen` returns null so the
* caller can render an honest placeholder (gate 19) instead of NaN.
* @param {string} iso ISO timestamp
* @param {Date|string} [refDate] reference moment (defaults to now)
* @returns {number|null} days (>= 0 when first_seen ≤ refDate), or null
 */
export function daysSince(iso, refDate = new Date()) {
  const t = ts(iso)
  if (!Number.isFinite(t)) return null
  const ref = toDate(refDate).getTime()
  const diff = ref - t
  // floor so a same-day / sub-day gap reads as 0; negative (future first_seen)
  // clamps to 0 so a card never says \"上線 -3 天\".
  return diff <= 0 ? 0 : Math.floor(diff / 86400000)
}

/**
 * Keep items whose `first_seen` falls within `days` of `refDate`. `period` may be
* a number (7/14/30 …) or 'all'/'*'/null (no time bound). Items without a usable
* `first_seen` are excluded for a numeric window and kept for 'all'.
* @param {Array} list
* @param {number|string} period days window, or 'all'
* @param {Date|string} [refDate]
* @returns {Array} filtered copy (never mutates the input)
 */
export function withinPeriods(list, period, refDate = new Date()) {
  const src = Array.isArray(list) ? list : []
  if (period == null || period === 'all' || period === '*') return src.slice()
  const days = Number(period)
  if (!Number.isFinite(days)) return src.slice()
  return src.filter((it) => {
    const ds = daysSince(it && it.first_seen, refDate)
    return ds != null && ds <= days
  })
}

/**
 * Sort items by `first_seen`. mode 'newest' (default) → newest first; 'oldest' →
* oldest first. Items without a usable `first_seen` always sink to the end (in
* either direction) so unknown dates never float to the top. Pure: returns a
* fresh array, never mutates the input.
* @param {Array} list
* @param {'newest'|'oldest'} [mode]
* @returns {Array}
 */
export function sortNew(list, mode = 'newest') {
  const src = Array.isArray(list) ? list : []
  const dir = mode === 'oldest' ? 1 : -1
  return src.slice().sort((a, b) => {
    const ta = ts(a && a.first_seen)
    const tb = ts(b && b.first_seen)
    if (Number.isNaN(ta) && Number.isNaN(tb)) return 0
    if (Number.isNaN(ta)) return 1
    if (Number.isNaN(tb)) return -1
    return (ta - tb) * dir
  })
}

/**
 * The new-arrivals list for a 時段 window, newest-first. Pure + null-safe.
* @param {number} [days] window (default 30)
* @param {Date|string} [refDate]
* @returns {Array} items with `first_seen` ≤ days, sorted newest → oldest
 */
export function newArrivals(days = 30, refDate = new Date()) {
  const items = withinPeriods(allItems, days, refDate)
  return sortNew(items, 'newest')
}

/**
 * Distinct, non-empty `tag` strings (the 類別 chips), in first-appearance order.
* Null-safe: null/empty/non-string tags are skipped.
* @param {Array} list
* @returns {string[]}
 */
export function categories(list) {
  const src = Array.isArray(list) ? list : []
  const seen = new Set()
  const out = []
  for (const it of src) {
    const t = it && it.tag
    if (typeof t === 'string' && t.trim() && !seen.has(t)) {
      seen.add(t)
      out.push(t)
    }
  }
  return out
}

/**
 * 省 $X amount for a card: the drop from the all-time high to the current price
* (`high − current`). Returns 0 when there is no positive drop (so a card only
* shows a 省 tag when `drop_pct_from_high > 0` — the discovery rule keeps savings
* a secondary signal, not the headline). Null-safe.
* @param {object} item
* @returns {number}
 */
export function savingsAmount(item) {
  if (!item || typeof item !== 'object') return 0
  const high = item.high
  const cur = item.current
  const h = Number(high)
  const c = Number(cur)
  if (!Number.isFinite(h) || !Number.isFinite(c)) return 0
  const diff = h - c
  return diff > 0 ? Math.round(diff) : 0
}

/**
 * Clean, emoji-free tag badges for one new-arrival card (gate 30a: the baked
* `verdict.label` carries emoji, so we never render it — we rebuild the text
* here). `refDate` drives the 上線 / 新到貨 badges so the card is testable.
* @param {object} item
* @param {Date|string} [refDate]
* @returns {{online: string|null, badges: string[]}}
*   online: \"上線 N 天\" primary label (null when first_seen is unknown),
*   badges: secondary badges — 新到貨 / 省 $X / 歷史最低 (may coexist, in that order).
 */
export function newArrivalTags(item, refDate = new Date()) {
  if (!item || typeof item !== 'object') return { online: null, badges: [] }
  const online = daysSince(item.first_seen, refDate)
  const onlineLabel = online == null ? '上線時間未知' : `上線 ${online} 天`

  const badges = []
  // 新到貨: first_seen within 14 days.
  if (online != null && online <= 14) badges.push('新到貨')
  // 省 $X: a positive drop from the high (savings is a secondary signal).
  const save = savingsAmount(item)
  if ((item.drop_pct_from_high || 0) > 0 && save > 0) badges.push(`省 $${formatTWD(save)}`)
  // 歷史最低: at the all-time_low.
  if (item.at_all_time_low) badges.push('歷史最低')
  return { online: onlineLabel, badges }
}
