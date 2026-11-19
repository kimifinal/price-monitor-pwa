/**
 * mvm.js — the MVM 檔期目錄 data + pure render helpers.
 *
 * The catalog (MvmCatalog.vue / MvmProductCard.vue) is a PURE renderer: it
 * never re-derives a price or a discount. The one source of truth is the
 * OFFLINE-BAKED snapshot `src/data/mvm.json` (a copy of the backend
 * `data/costco_mvm/2026-11-16_mvm_p4.json`), so the catalog renders 6 檔期
 * with ZERO network — fully offline-safe for the PWA (mirrors how
 * history.js bakes+loads the 比價 snapshot).
 *
 * Data shape (backend SSOT):
 *   tabs[].{ tab_id, label, period, n_products, description, price_type,
 *            products: [{ sku, name, cat, type, orig, promo, discount, note? }] }
 *   price_types: { online_only | store_online_diff | store_only:
 *                 { label, badge, meaning } }
 *
 * Two real quirks of the baked data (handled here, not in the template):
 *  • A tab's `n_products` may be a non-integer note (e.g. "~10 (已於前次抓取)")
 *    or 0. Those are not a real count → the UI shows "N/A" (never an em-dash —
 *    sloplint gate 19).
 *  • A product's `orig`/`discount` may be null (秤賣 / 特例品項) → the card
 *    shows "N/A" for the missing figure (gate 19).
 *
 *  • A product's `type` may be a sub-variant the global `price_types` map does
 *    not key directly (e.g. "store_only_weight", "store_only_special"). The
 *    badge falls back to the "store_only" base so a sub-variant never renders
 *    empty.
 */
import mvmData from '../data/mvm.json'

/**
 * The catalog snapshot, as the baked JSON is shipped. Pure + synchronous so the
 * UI mounts it with no async dance and no network (offline-first).
 * @returns {{ tabs: Array<object>, priceTypes: object<string,object>, sourceDate: string }}
 */
export function loadMvmCatalog() {
  // Normalize so EVERY 檔期 carries a `products` array — a couple of empty 檔期 in
  // the snapshot have no `products` key at all. Downstream (the lazy grid +
  // isEmptyTab) then treats a missing-tab and an empty-tab identically.
  const rawTabs = Array.isArray(mvmData.tabs) ? mvmData.tabs : []
  return {
    tabs: rawTabs.map((t) =>
      t && t.products == null
        ? { ...t, products: [] }
        : Array.isArray(t.products)
          ? t
          : { ...t, products: [] },
    ),
    priceTypes: mvmData.price_types || {},
    sourceDate: mvmData.source_date || '',
  }
}

/**
 * Which tab is active on mount. `initialTab` wins when it names a real tab;
 * otherwise the first tab that actually carries products (an empty tab should
 * not own the first screen); else the very first tab.
 * @param {Array<object>} tabs
 * @param {string} [initialTab]
 * @returns {string} a tab_id
 */
export function defaultActiveTab(tabs, initialTab) {
  const list = Array.isArray(tabs) ? tabs : []
  if (initialTab && list.some((t) => t && t.tab_id === initialTab)) return initialTab
  const firstWithProducts = list.find((t) => t && Array.isArray(t.products) && t.products.length > 0)
  const chosen = firstWithProducts || list[0] || { tab_id: '' }
  return chosen.tab_id
}

/**
 * Discount % from orig→promo. Pure + null-safe: a missing orig (秤賣/特例) or a
 * null discount yields null so the card can show "N/A" instead of a bogus 0% or
 * "-0.0%". Rounds to one decimal — TWD money has no sub-unit, but the ratio is a
 * measurement, so one decimal (gate 64: a figure, not costume type).
 * @param {object} product
 * @returns {number|null} discount percent, or null when it cannot be computed
 */
export function discountPct(product) {
  if (!product || typeof product !== 'object') return null
  const orig = product.orig
  const discount = product.discount
  if (orig == null || orig <= 0 || discount == null) return null
  return Math.round((discount / orig) * 1000) / 10 // one decimal, no toFixed (gate AC1b)
}

/**
 * Colour tier for a discount %, via the design tokens (style.css):
 *   ≥25%   success (deep green)    · 15–25% good-deal (lighter green)
 *   <15%   text-2 (muted, "no special")   · null → low (no figure to colour).
 * The card only names the token class; the hex lives in style.css.
 * @param {number|null} pct
 * @returns {'high'|'mid'|'low'}
 */
export function discountTier(pct) {
  if (pct == null || Number.isNaN(pct)) return 'low'
  if (pct >= 25) return 'high'
  if (pct >= 15) return 'mid'
  return 'low'
}

/**
 * The count badge on a 檔期 tab. A real positive integer count renders as its
 * string; anything else (a ~note, 0, or missing) renders "N/A" — never an
 * em-dash (sloplint gate 19 forbids "—"; "N/A" keeps the count column tidy and
 * honest about "count not yet known").
 * @param {object} tab
 * @returns {string} count string or 'N/A'
 */
export function tabCountText(tab) {
  if (!tab || typeof tab !== 'object') return 'N/A'
  const n = tab.n_products
  return Number.isInteger(n) && n > 0 ? String(n) : 'N/A'
}

/** Whether a 檔期 tab has no products to render (drives the dimmed .tab-empty). */
export function isEmptyTab(tab) {
  return !tab || !Array.isArray(tab.products) || tab.products.length === 0
}

/**
 * Resolve a product's badge: its `type` looked up in `priceTypes`, falling back
 * to the "store_only" base for sub-variants the map does not key directly
 * (store_only_*). Returns the base key so the badge class + colour stay stable,
 * plus the label/meaning to render.
 * @param {object} product
 * @param {object<string,object>} priceTypes
 * @returns {{ key: string, label: string, meaning: string }}
 */
export function productBadge(product, priceTypes) {
  const types = priceTypes || {}
  const raw = product && product.type
  const key = raw && types[raw] ? raw : raw && types[raw.replace(/_(weight|special)$/, '')] ? raw.replace(/_(weight|special)$/, '') : 'store_only'
  const meta = types[key] || {}
  return { key, label: meta.label || key, meaning: meta.meaning || '' }
}

/**
 * Sort the active tab's products. `discount` (default) = deepest discount first;
 * `category` = grouped by class then name; `price` = highest promo first.
 * Null-safe: a product with no computable discount sinks to the bottom on the
 * discount sort (it loses the 0-vs-real comparison). Pure + non-mutating.
 * @param {Array<object>} products
 * @param {'discount'|'category'|'price'} [mode='discount']
 * @returns {Array<object>} a new, sorted array
 */
export function sortProducts(products, mode = 'discount') {
  const list = Array.isArray(products) ? products : []
  const out = [...list]
  if (mode === 'category') {
    out.sort((a, b) => {
      const byCat = String(a && a.cat || '').localeCompare(String(b && b.cat || ''))
      return byCat || String(a && a.name || '').localeCompare(String(b && b.name || ''))
    })
  } else if (mode === 'price') {
    out.sort((a, b) => (b && b.promo != null ? b.promo : 0) - (a && a.promo != null ? a.promo : 0))
  } else {
    out.sort((a, b) => (discountPct(b) || 0) - (discountPct(a) || 0))
  }
  return out
}

/** Filter a tab's products to one category, or keep all when `cat` is 'all'. */
export function filterByCategory(products, cat) {
  const list = Array.isArray(products) ? products : []
  if (!cat || cat === 'all') return list
  return list.filter((p) => p && p && p.cat === cat)
}

/** Distinct, sorted category names present in a tab's products (filter chips). */
export function categoriesOf(products) {
  const set = new Set()
  for (const p of Array.isArray(products) ? products : []) {
    if (p && p.cat) set.add(p.cat)
  }
  return Array.from(set).sort()
}
