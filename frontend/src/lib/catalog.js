/**
 * catalog.js — the 全部商品 全庫 catalog data + pure render helpers (#50).
 *
 * The 全部商品 tab is a PURE renderer over the OFFLINE-BAKED snapshot
 * `src/data/catalog.json` (10,049 items, derived from the backend
 * `data/costco_catalog/products.full.json`), so it renders the whole 全庫 with
 * ZERO network — fully offline-safe for the PWA (mirrors how mvm.js / history.js
 * bake + load their snapshots).
 *
 * Data shape (baked catalog.json):
 *   { products: [{ sku, name, price, basePrice, discount, online_only, stock }] }
 *
 *   • `online_only` (bool): true when 'Costco好市多網路獨家商品' was in the item's
 *     decals (the 4,693 網路獨家 items). false → a 賣場 (store) item. The source
 *     JSON carries no separate online price, so an online-only item's single
 *     `price` IS its 線上 price; a store item may carry a discounted `price`
 *     below its `basePrice` (the 246 限時特價 items).
 *   • `price`/`basePrice` may be null (a 秤賣 / 特例品項) → the card reads "N/A"
 *     (never "—" — sloplint gate 19). `discount` is the 省 amount (0 when none).
 *   • 賣場/線上 is the ONE toggle in the app; this module is its single source of
 *     truth for filtering + the count-bar / price-line text, so a template never
 *     re-derives a number.
 *
 * Everything here is PURE + null-safe (gate 19: a missing figure reads "N/A",
 * never an em-dash), so the card / view render a line-icon catalog without any
 * number computed in a template.
 */
import catalogData from '../data/catalog.json'
// TWD grouping lives in ONE place (format.js, issue #25). The catalog card shows
// a "$" sign (the mockup), so it reuses formatTWD for the 千分位 grouping and
// prefixes "$" itself — grouping stays single-source, no second formatter.
import { formatTWD } from './format.js'

/**
 * The baked 全庫, as the JSON is shipped. Pure + synchronous so the UI mounts it
 * with no async dance and no network (offline-first). Non-object entries are
 * normalized to a null-safe record (every figure "N/A", discount 0, not
 * online-only) so a malformed row can never crash a render.
 * @returns {Array<object>} a new, normalized array of catalog products
 */
export function loadCatalog() {
  const raw = Array.isArray(catalogData.products) ? catalogData.products : []
  return raw.map((p) =>
    p && typeof p === 'object'
      ? p
      : {
          sku: null,
          name: 'N/A',
          price: null,
          basePrice: null,
          discount: 0,
          online_only: false,
          stock: 'N/A',
        },
  )
}

/** Whether this item is a 網路獨家 (online-only) item. Null-safe. */
export function isOnlineOnly(p) {
  return p && p.online_only === true
}

/**
 * Filter the 全庫 by mode: 'store' = 賣場 items only (hide the 網路獨家 ones);
 * 'online' = the WHOLE 全庫 (every item). Pure + null-safe; never mutates.
 * @param {Array<object>} products
 * @param {'store'|'online'} [mode='store']
 * @returns {Array<object>} a new, filtered array
 */
export function filterByMode(products, mode = 'store') {
  const list = Array.isArray(products) ? products : []
  if (mode === 'online') return list
  return list.filter((p) => !isOnlineOnly(p))
}

/**
 * The three counts the 賣場/線上 toggle + count bar read: total / store /
 * onlineOnly. Pure + null-safe.
 * @param {Array<object>} products
 * @returns {{total:number,store:number,onlineOnly:number}}
 */
export function catalogStats(products) {
  const all = Array.isArray(products) ? products : []
  const onlineOnly = all.filter(isOnlineOnly).length
  const store = all.length - onlineOnly
  return { total: all.length, store, onlineOnly }
}

/**
 * The count-bar text under the 賣場/線上 toggle.
 *   store  mode → "5,356 筆賣場可購 · 4,693 項線上 專 屬已隱藏"
 *   online mode → "10,049 筆全庫 · 含 4,693 項線上 專 屬"
 * A zero-count mode reads "N/A" (gate 19, never "—"). Grouping via formatTWD.
 * @param {Array<object>} products
 * @param {'store'|'online'} [mode='store']
 * @returns {string}
 */
export function countBarText(products, mode = 'store') {
  const { total, store, onlineOnly } = catalogStats(products)
  if (mode === 'online') {
    return total > 0
      ? `${formatTWD(total)} 筆全庫 · 含 ${formatTWD(onlineOnly)} 項線上 專 屬`
      : 'N/A'
  }
  return store > 0
    ? `${formatTWD(store)} 筆賣場可購 · ${formatTWD(onlineOnly)} 項線上 專 屬已隱藏`
    : 'N/A'
}

/**
 * The "約 X 折" 個位 for a catalog item, from price→basePrice (a catalog item's
 * 促價 vs 原價 — the opposite direction of mvm.js's zheOf, which uses orig/promo).
 * Pure + null-safe: a missing/≤0 price or base, or no discount (price ≥ base),
 * yields null so the card hides the chip instead of a bogus 折. TWD has no minor
 * unit, so the ratio rounds to a whole 折 (one digit): 121/1000→1, 5199/6899→8,
 * 349/439→8.
 * @param {object} product
 * @returns {number|null} the 個位 折 (1..10+ normally), or null when uncomputable
 */
export function zheOfCatalog(product) {
  if (!product || typeof product !== 'object') return null
  const price = product.price
  const base = product.basePrice
  if (price == null || base == null || !Number.isFinite(price) || !Number.isFinite(base) || base <= 0 || price <= 0) return null
  if (price >= base) return null // no discount, no zhe
  return Math.round((price / base) * 10)
}

/**
 * The main price a card shows for a mode. A catalog item carries a single `price`
 * (its 促價 in both modes; an online-only item's only price), so the main figure
 * is `price` regardless of mode — the MODE difference is the badge + the blue tint
 * on a discounted item in online mode, not the figure itself. Null-safe.
 * @param {object} product
 * @param {'store'|'online'} [mode='store']
 * @returns {number|null}
 */
export function mainPrice(product, mode = 'store') {
  const p = product && typeof product === 'object' ? product : {}
  return p.price != null ? p.price : null
}

/**
 * The "省 $X" savings text, when the item carries a positive discount. Pure +
 * null-safe: a missing / 0 / negative discount renders '' (no chip). Grouping via
 * formatTWD.
 * @param {object} product
 * @returns {string}
 */
export function saveText(product) {
  if (!product || typeof product !== 'object') return ''
  const d = product.discount
  if (d == null || d <= 0) return ''
  return `省 $${formatTWD(d)}`
}

/**
 * The card's price line for a mode.
 *   store  mode                → "賣場 $X"            (X = the item's price)
 *   online mode, 網路獨家 item  → "線上 $X"            (its only price)
 *   online mode, store item    → "賣場 $base · 線上 $price" when discounted
 *                                (a 限時特價 促價 below 原價), else "線上 $X"
 * Pure + null-safe: a missing figure reads "N/A" (no "—", gate 19), a "$" prefix
 * on a real figure matches the mockup, grouping reuses formatTWD (the TWD SSOT).
 * @param {object} product
 * @param {'store'|'online'} [mode='store']
 * @returns {string}
 */
export function catalogPriceLine(product, mode = 'store') {
  const p = product && typeof product === 'object' ? product : {}
  const money = (n) => (n == null ? 'N/A' : '$' + formatTWD(n))
  const price = p.price
  const base = p.basePrice
  const online = isOnlineOnly(p)
  if (mode === 'store') {
    return `賣場 ${money(price)}`
  }
  // online mode
  if (online) {
    return `線上 ${money(price)}`
  }
  // store item in online mode: show both when it carries a 促價 below its 原價,
  // else just the 線上 figure (its single price).
  if (base != null && base > 0 && price != null && price < base) {
    return `賣場 ${money(base)} · 線上 ${money(price)}`
  }
  return `線上 ${money(price)}`
}

/**
 * Slice a window of up to `pageSize` items starting at page `page` (0-indexed).
 * Pure + null-safe; never mutates. Used by the 全部 view's "顯示更多" pagination.
 * @param {Array<object>} products
 * @param {number} [page=0]
 * @param {number} [pageSize=50]
 * @returns {Array<object>}
 */
export function paginate(products, page = 0, pageSize = 50) {
  const list = Array.isArray(products) ? products : []
  const start = page * pageSize
  return list.slice(start, start + pageSize)
}

/** Whether more pages exist beyond `page` (drives the "顯示更多" button). */
export function hasMore(products, page, pageSize = 50) {
  return Array.isArray(products) ? products.length > (page + 1) * pageSize : false
}
