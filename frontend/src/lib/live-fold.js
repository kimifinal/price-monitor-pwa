/**
 * live-fold.js — issue #23: collapse + 3-state filter for the 即時比價 (live)
 * section, so the DOM carries ≤ FOLD_LIMIT cards on first paint instead of all
 * 52. Pure functions (zero DOM), reusing the verdict SSOT in monitor.js, so the
 * filter/fold decisions stay byte-identical to the rest of the app.
 *
 * Contract (design §5.1 / B5, Tier 3):
 *   觸發 (isTriggered) = "worth buying now" = all_time_low ∪ good_deal
 *   近低點 (isNearLow) = good_deal — a SUBSET of triggered (≥15% off the high).
 *   The UI label is "近低點" (not "觸發") so the two chips never read the same.
 *
 * We import ONLY priceVerdict: the verdict logic is the single source of truth
 * (monitor.js mirrors backend/models.py), so live-fold never re-derives a drop
 * or a verdict — it just maps the verdict back onto the live card objects.
 */
import { priceVerdict } from './monitor.js'

/**
 * A live card is "triggered" (buy-now) when its verdict is all_time_low or
 * good_deal. Defends against junk (null card / missing metrics → unknown → false).
 * @param {object} card
 * @returns {boolean}
 */
export function isTriggered(card) {
  const v = priceVerdict(card?.metrics)?.verdict
  return v === 'all_time_low' || v === 'good_deal'
}

/**
 * A live card is "near low" when its verdict is good_deal (≥15% off the recent
 * high). This is a strict subset of isTriggered, so the near-low chip always
 * yields ≤ the triggered chip.
 * @param {object} card
 * @returns {boolean}
 */
export function isNearLow(card) {
  return priceVerdict(card?.metrics)?.verdict === 'good_deal'
}

// The three filter states. Unknown filter keys fall through to 'all' below, so a
// stale/typo'd filter never silently blanks the section.
const FILTERS = {
  all: () => true,
  triggered: (c) => isTriggered(c),
  'near-low': (c) => isNearLow(c),
}

/**
 * Filter the live cards by one of the three states, defaulting to 'all'. An
 * unknown filter key or non-array input yields an empty array / all, defensively,
 * so the caller's empty-fallback (App.vue) keeps the section rendering.
 * @param {Array<object>} cards
 * @param {'all'|'triggered'|'near-low'} [filter='all']
 * @returns {Array<object>}
 */
export function filterLive(cards, filter = 'all') {
  const fn = FILTERS[filter] ?? FILTERS.all
  return (Array.isArray(cards) ? cards : []).filter(fn)
}

/** Default number of visible live cards before the rest fold away. */
export const FOLD_LIMIT = 6

/**
 * Fold a card list to `limit` visible cards unless `expanded` (then show all).
 * Returns the visible slice + how many are folded so the UI can offer a
 * "expand the rest" toggle. Non-array input yields a fully-empty result.
 * @param {Array<object>} cards
 * @param {{expanded?: boolean, limit?: number}} [opts]
 * @returns {{visible: Array<object>, foldedCount: number, total: number}}
 */
export function foldCards(cards, { expanded = false, limit = FOLD_LIMIT } = {}) {
  const arr = Array.isArray(cards) ? cards : []
  if (expanded || arr.length <= limit) {
    return { visible: arr, foldedCount: 0, total: arr.length }
  }
  return { visible: arr.slice(0, limit), foldedCount: arr.length - limit, total: arr.length }
}
