/**
 * storage.js — a thin, testable wrapper over localStorage.
 *
 * Isolated so the UI never talks to `window.localStorage` directly: that makes
 * unit tests runnable without a DOM (they can mock this module) and the SSR
 * path safe (window may not exist).
 */

const KEY = 'price-monitor.items'

/**
 * @returns {import('./monitor.js').Item[]}
 */
export function loadItems() {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * @param {import('./monitor.js').Item[]} items
 * @returns {boolean} true if the write succeeded
 */
export function saveItems(items) {
  if (typeof window === 'undefined' || !window.localStorage) return false
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items))
    return true
  } catch {
    return false
  }
}

/**
 * @param {number} ttlMs
 * @param {string} value
 * @returns {boolean}
 */
export function setCookie(name, value, ttlMs) {
  if (typeof document === 'undefined') return false
  try {
    const maxAge = Math.max(1, Math.floor(ttlMs / 1000))
    document.cookie = `${name}=${encodeURIComponent(value)};max-age=${maxAge};path=/;SameSite=Lax`
    return true
  } catch {
    return false
  }
}

// Expose the storage key so tests/coders know where data lives.
export const STORAGE_KEY = KEY
