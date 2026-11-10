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
