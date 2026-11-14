/**
 * watchlist.js — the #4 個人化 (per-item) alert GATE, mirrored from
 * `backend/watchlist.py`.
 *
 * The verdict stays the single SSOT in monitor.js (`priceVerdict`, and
 * `shouldAlert` for a target price). This module decides ONLY which watched skus
 * may come through, and each item's per-item threshold (a target price and/or a
 * minimum drop-from-high %). It is fully OFFLINE: a static seed (`DEFAULT_WATCHLIST`,
 * mirroring `backend/watchlist.json`) plus a localStorage edit — never a server
 * round-trip.
 *
 * The three guarantees the frontend honors, matching the backend:
 *   * an item may alert only if it is in the watchlist AND meets its threshold;
 *   * an unwatched sku never alerts, even at an all-time low;
 *   * an empty watchlist is silent (no alerts).
 */

// The ONE price rule (SSOT) — a target price reuses it, never a second rule.
import { shouldAlert } from './monitor.js'

/**
 * A watchlist entry.
 * @typedef {{sku: string|number, name?: string,
 *            threshold?: {target?: number, min_drop_pct?: number}}} WatchEntry
 */

// localStorage key (isolated from the legacy items store in storage.js).
const KEY = 'price-monitor.watchlist'
export const WATCHLIST_KEY = KEY

// A static offline seed — a small, sensible subset mirroring backend/watchlist.json.
// No fetch: the PWA works fully offline from this default; localStorage then lets a
// user edit it without a server round-trip.
export const DEFAULT_WATCHLIST = [
  { sku: '149699', name: 'ANKER A2674 336 GaN 67W 急速充電器 2入組', threshold: { target: 1069 } },
  { sku: '153876', name: 'JBL Live 670NC 耳罩式降噪藍牙耳機', threshold: { target: 1899 } },
  { sku: '161367', name: 'Soundcore AeroClip 開放式藍牙耳夾耳機', threshold: { target: 2079 } },
  { sku: '153526', name: '飛利浦 55吋 4K QLED Google TV 顯示器 55PQT8530/96', threshold: { target: 12599 } },
  { sku: '156974', name: 'iClever BTH18 炫光無線兒童耳機', threshold: { target: 849 } },
  { sku: '162427', name: 'Hawk 360° 旋轉升降螢幕架 附抽屜', threshold: { target: 669 } },
]

// Deep-clone one entry so edits never mutate a passed-in prop or the seed.
function cloneEntry(e) {
  if (!e || typeof e !== 'object') return null
  return e.threshold ? { ...e, threshold: { ...e.threshold } } : { ...e }
}

// Deep-clone a list of entries.
export function cloneWatchlist(entries) {
  return (Array.isArray(entries) ? entries : []).map(cloneEntry).filter(Boolean)
}

/**
 * Load the watchlist from localStorage, falling back to the static seed.
 * @returns {WatchEntry[]}
 */
export function loadWatchlist() {
  if (typeof window === 'undefined' || !window.localStorage) return cloneWatchlist(DEFAULT_WATCHLIST)
  try {
    const raw = window.localStorage.getItem(WATCHLIST_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) ? cloneWatchlist(parsed) : cloneWatchlist(DEFAULT_WATCHLIST)
  } catch {
    return cloneWatchlist(DEFAULT_WATCHLIST)
  }
}

/**
 * Persist the watchlist to localStorage (offline). @returns {boolean} success.
 * @param {WatchEntry[]} entries
 */
export function saveWatchlist(entries) {
  if (typeof window === 'undefined' || !window.localStorage) return false
  try {
    window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(entries))
    return true
  } catch {
    return false
  }
}

/**
 * Reset to the static seed and persist it. @returns {WatchEntry[]}
 */
export function resetWatchlist() {
  const seed = cloneWatchlist(DEFAULT_WATCHLIST)
  saveWatchlist(seed)
  return seed
}

/**
 * Does item `m` satisfy its own per-item threshold? Mirrors the backend exactly.
 *
 *   * `target`       => reuse shouldAlert (the one price rule: price <= target);
 *   * `min_drop_pct`  => `dropPctFromHigh >= min_drop_pct` (the sku's OWN drop);
 *   * both present    => BOTH must hold; neither present => no gate.
 * @param {{price?: number, dropPctFromHigh?: number}|null|undefined} m
 * @param {WatchEntry|null} entry
 * @returns {boolean}
 */
export function thresholdMet(m, entry) {
  if (!entry || !entry.threshold) return true
  const th = entry.threshold
  if (th.target != null) {
    const price = m?.price
    if (price == null) return false
    // reuse the SSOT price rule — never a second one
    if (!shouldAlert({ price, target: Number(th.target) })) return false
  }
  if (th.min_drop_pct != null) {
    const drop = m?.dropPctFromHigh ?? 0
    if (drop < Number(th.min_drop_pct)) return false
  }
  return true
}

/**
 * The watchlist entry whose sku matches an item, or null when unwatched.
 * Skus compare as strings, so '149699' and 149699 gate the same item.
 * @param {{sku?: string|number}} m
 * @param {WatchEntry[]|null|undefined} watchlist
 * @returns {WatchEntry|null}
 */
export function findEntry(m, watchlist) {
  if (!Array.isArray(watchlist) || !m || m.sku == null) return null
  const sku = String(m.sku)
  return watchlist.find((e) => e && e.sku != null && String(e.sku) === sku) || null
}

/**
 * The full #4 gate: item `m` may alert only if it is WATCHED and its threshold is
 * met. A null/undefined watchlist disables the gate; an empty list is the silent
 * default (nothing passes).
 * @param {{sku?: string|number, price?: number, dropPctFromHigh?: number}} m
 * @param {WatchEntry[]|null|undefined} watchlist
 * @returns {boolean}
 */
export function wouldAlert(m, watchlist) {
  if (watchlist == null) return true            // gate disabled
  const entry = findEntry(m, watchlist)
  if (!entry) return false                      // not watched
  return thresholdMet(m, entry)
}

// =====================================================================
// #11: portable watchlist — export / import  (all offline, no network)
// =====================================================================

/**
 * Serialize a watchlist to a JSON string.
 * Semantically matches backend `watchlist.save()`: same shape
 * `{sku, name?, threshold?:{target?, min_drop_pct?}}`, dedup by sku (last-wins),
 * threshold keys filtered to the known set, JSON-indented 1-space like the
 * backend `json.dumps(..., indent=1)`. Pure — no side effects.
 *
 * @param {WatchEntry[]} list
 * @returns {string}  A JSON string (+ trailing newline)
 */
export function serializeWatchlist(list) {
  const map = new Map() // last-wins dedup
  for (const e of (Array.isArray(list) ? list : [])) {
    if (!e || e.sku == null) continue
    const sku = String(e.sku)
    map.set(sku, { sku, name: e.name, threshold: e.threshold })
  }
  const clean = [...map.values()].map((e) => {
    const out = { sku: e.sku }
    if (e.name != null) out.name = String(e.name)
    if (e.threshold && typeof e.threshold === 'object' && !Array.isArray(e.threshold)) {
      const th = {}
      if (e.threshold.target != null && !Number.isNaN(Number(e.threshold.target))) {
        th.target = Number(e.threshold.target)
      }
      if (e.threshold.min_drop_pct != null && !Number.isNaN(Number(e.threshold.min_drop_pct))) {
        th.min_drop_pct = Number(e.threshold.min_drop_pct)
      }
      if (Object.keys(th).length > 0) out.threshold = th
    }
    return out
  })
  // 1-space indent mirrors the backend json.dumps(..., indent=1); trailing newline
  return JSON.stringify(clean, null, 1) + '\n'
}

/**
 * Create a Blob from a watchlist for an offline download.
 * Returns null if `Blob` is unavailable (SSR/test without global).
 * Pure — does not call URL.createObjectURL (the UI does that).
 *
 * @param {WatchEntry[]} list
 * @returns {Blob|null}
 */
export function buildExportBlob(list) {
  if (typeof Blob === 'undefined') return null
  return new Blob([serializeWatchlist(list)], { type: 'application/json' })
}

/**
 * Parse a JSON string back into a valid watchlist with full input validation.
 *
 * Accepts a JSON array of entry-like objects.
 * - Invalid JSON syntax        → { entries: [], errors: [{ error }] }
 * - non-array root            → { entries: [], errors: [{ error }] }
 * - entry without sku          → skipped, error recorded
 * - threshold keys filtered to {target, min_drop_pct}
 * - dedup by sku, last-wins
 *
 * @param {string} jsonStr
 * @returns {{ entries: WatchEntry[], errors: Array<{ sku?: string, error: string }> }}
 */
export function deserializeWatchlist(jsonStr) {
  const errors = []
  let raw
  try {
    raw = JSON.parse(jsonStr)
  } catch (e) {
    return { entries: [], errors: [{ error: `無效 JSON: ${e.message}` }] }
  }
  const input = Array.isArray(raw) ? raw : null
  if (!input) {
    return { entries: [], errors: [{ error: 'JSON 根節點必須是陣列' }] }
  }
  const map = new Map() // sku → entry, last-wins
  for (const item of input) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      errors.push({ sku: String(item ?? ''), error: '不是物件' })
      continue
    }
    const sku = item.sku
    if (sku == null || sku === '') {
      errors.push({ sku: String(sku), error: '缺少 sku' })
      continue
    }
    const key = String(sku)
    const out = { sku: key }
    if (item.name != null) out.name = String(item.name)
    if (
      item.threshold &&
      typeof item.threshold === 'object' &&
      !Array.isArray(item.threshold)
    ) {
      const th = {}
      if (item.threshold.target != null && !Number.isNaN(Number(item.threshold.target))) {
        th.target = Number(item.threshold.target)
      }
      if (
        item.threshold.min_drop_pct != null &&
        !Number.isNaN(Number(item.threshold.min_drop_pct))
      ) {
        th.min_drop_pct = Number(item.threshold.min_drop_pct)
      }
      if (Object.keys(th).length > 0) out.threshold = th
    }
    map.set(key, out)
  }
  return { entries: [...map.values()], errors }
}
