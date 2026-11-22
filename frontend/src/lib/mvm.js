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
// TWD grouping lives in ONE place (format.js, issue #25). The warm mobile card
// shows a "$" sign (the mockup), so it reuses formatTWD for the 千分位 grouping
// and prefixes "$" itself — grouping stays single-source, no second formatter.
import { formatTWD } from './format.js'

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

// ---------------------------------------------------------------------------
// Warm mobile shell (案 B / #49) — two NEW pure helpers for the MVM 檔期 view.
// Both stay PURE + null-safe (gate 19: missing figures read "N/A", never "—") so
// the warm card / catalog can render a line-icon heading without re-deriving a
// number in a template.
// ---------------------------------------------------------------------------

/**
 * The "約 X 折" 折扣個位 from orig→promo. Pure + null-safe: a missing/≤0 orig or
 * promo yields null so the card shows "N/A" instead of a bogus 0 折. TWD has no
 * minor unit, so the ratio is rounded to a whole 折 (one digit). 121/1000→1,
 * 329/349→9, 919/1149→8. No clamp: a promo over orig keeps its (unlikely) value.
 * @param {object} product
 * @returns {number|null} the 個位 折 (1..10+ normally), or null when uncomputable
 */
export function zheOf(product) {
  if (!product || typeof product !== 'object') return null
  const orig = product.orig
  const promo = product.promo
  if (orig == null || promo == null || !Number.isFinite(orig) || !Number.isFinite(promo) || orig <= 0 || promo <= 0) return null
  return Math.round((promo / orig) * 10)
}

// "到 MM/DD" from a period like "2026/10/26 ~ 11/20": the 結束日 is the LAST
// "~" segment, resolved to a calendar day (a bare "M/D" takes the start's year).
function startYearOf(period) {
  const first = String(period || '').split('~')[0].trim()
  const m = /(\d{4})\s*\/\s*(\d{1,2})\s*\/\s*(\d{1,2})/.exec(first)
  return m ? +m[1] : null
}
function toMDY(year, month, day) {
  if (!Number.isFinite(year)) return null
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  return { year, month, day }
}
function parsePeriodEnd(period, refYear) {
  if (!period || typeof period !== 'string') return null
  const endStr = String(period.split('~').pop().trim())
  const full = /^(\d{4})\s*\/\s*(\d{1,2})\s*\/\s*(\d{1,2})$/.exec(endStr)
  if (full) return toMDY(+full[1], +full[2], +full[3])
  const md = /^(\d{1,2})\s*\/\s*(\d{1,2})$/.exec(endStr)
  if (md) return toMDY(startYearOf(period) || refYear || new Date().getFullYear(), +md[1], +md[2])
  return null
}
const pad2 = (n) => String(n).padStart(2, '0')

/**
 * The MVM 檔期's short "MM/DD ~ MM/DD" range for the chip slider's lower line,
 * or "敬請期待" when the period has no parseable date. Kimi 2026-11-22: the
 * chip shows the full two-date range instead of "到 MM/DD", and a date-less 檔期
 * ("黑色購物週" / "網購星期一") reads "敬請期待", not blank. Pure + null-safe;
 * strips an optional leading "YYYY/" so "2026/10/26 ~ 11/22" → "10/26 ~ 11/22".
 * @param {object} [tab]
 * @returns {string} "MM/DD ~ MM/DD" or "敬請期待"
 */
export function periodShort(tab) {
  if (!tab || typeof tab !== 'object') return '敬請期待'
  const p = String(tab.period || '').trim()
  if (!p || p === 'N/A' || p === '敬請期待') return '敬請期待'
  return p.replace(/^\d{4}\s*\//, '')
}

/**
 * The MVM 檔期 section header: `N 筆 · 檔期名 · MM/DD ~ MM/DD · 剩 K 天` (or
 * `N 筆 · 檔期名 · 敬請期待` when no date). Count prefers
 * the tab's `n_products` when it is a real positive integer, else the number of
 * items actually listed, else "N/A" (gate 19, never "—"). The 到期日 range is
 * parsed from `period` via `periodShort`; `daysLeft` = end − today, clamped at 0
 * (a past 檔期 reads "剩 0 天"). `refDate` is injectable so a test pins "today"
 * without waiting a real day — the UI passes none and gets the live clock. A
 * tab whose period is not a date ("敬請期待") yields end "N/A", no 剩-clause
 * (null daysLeft), and text ending in "敬請期待".
 * @param {object} tab
 * @param {Date} [refDate]
 * @returns {{count:string,label:string,end:string,range:string,daysLeft:(number|null),text:string}}
 */
export function sectionHeader(tab, refDate) {
  const t = tab && typeof tab === 'object' ? tab : {}
  const ref = refDate instanceof Date ? refDate : new Date()

  const nProducts = t.n_products
  const listed = Array.isArray(t.products) ? t.products.length : 0
  let count
  if (Number.isInteger(nProducts) && nProducts > 0) count = `${nProducts} 筆`
  else if (listed > 0) count = `${listed} 筆`
  else count = 'N/A'

  const end = parsePeriodEnd(t.period, ref.getFullYear())
  const endText = end ? `${pad2(end.month)}/${pad2(end.day)}` : 'N/A'
  const range = periodShort(t)

  let daysLeft = null
  if (end) {
    const endDay = new Date(end.year, end.month - 1, end.day)
    const today = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate())
    daysLeft = Math.max(0, Math.round((endDay - today) / 86400000))
  }

  const label = t.label != null ? String(t.label) : 'N/A'
  const text =
    daysLeft == null
      ? `${count} · ${label} · ${range}`
      : `${count} · ${label} · ${range} · 剩 ${daysLeft} 天`

  return { count, label, end: endText, range, daysLeft, text }
}

/**
 * Whether a 檔期 has already ENDED: its parsed 結束日 (from `period`) is strictly
 * BEFORE `refDate` (defaults to today). A 檔期 with NO parseable end date
 * ("敬請期待" / blank) is NEVER expired, since an unknown / ongoing window cannot be
 * judged past. An 結束日 equal to today is still LIVE (not expired), so the day a
 * 檔期 runs is shown. Pure + null-safe (gate 19); reuses the existing
 * parsePeriodEnd / startYearOf / toMDY so the date math stays single-sourced.
 * @param {object} tab
 * @param {Date} [refDate]
 * @returns {boolean}
 */
export function isPeriodExpired(tab, refDate) {
  const ref = refDate instanceof Date ? refDate : new Date()
  const end = parsePeriodEnd(tab && tab.period, ref.getFullYear())
  if (!end) return false // a date-less / unparseable 檔期 is never "expired"
  const endDay = new Date(end.year, end.month - 1, end.day)
  const today = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate())
  return endDay < today // strictly before today; 結束日 == today is still live
}

/**
 * The 檔期 to actually OFFER: drop ONLY the 已過期 ones (Kimi's ask, an expired
 * 檔期 is removed rather than shown). Everything else stays, INCLUDING
 * empty-but-future 檔期: only expiration filters, so an empty future 檔期 is
 * still a real 檔期 to open. Pure + null-safe; reuses isPeriodExpired so "today"
 * stays injectable.
 * @param {Array<object>} tabs
 * @param {Date} [refDate]
 * @returns {Array<object>} a filtered copy (never mutates the input)
 */
export function activePeriods(tabs, refDate) {
  const list = Array.isArray(tabs) ? tabs : []
  return list.filter((t) => !isPeriodExpired(t, refDate))
}

/**
 * The card's last line: `買場 $X · 線上 $Y` for an online-eligible item (the 買場
 * figure is the struck 原價, 線上 is the 促價), or `買場 $X · 買場 $Y` for a
 * store-only 檔期 (no 線上 price to compare). Pure + null-safe: a missing figure
 * reads "N/A" (no "—", gate 19), a "$" prefix on a real figure matches the
 * mockup, and grouping reuses formatTWD (the TWD SSOT). `tabPriceType` lets a
 * store-only 檔期 with typeless items resolve to the 買場·買場 form.
 * @param {object} product
 * @param {string} [tabPriceType]
 * @returns {string}
 */
export function priceLine(product, tabPriceType = '') {
  const p = product && typeof product === 'object' ? product : {}
  const type = p.type
  const storeOnly =
    /^store_only/.test(String(type || '')) ||
    (type == null && tabPriceType === 'store_only')
  const money = (n) => (n == null ? 'N/A' : '$' + formatTWD(n))
  const orig = p.orig
  const promo = p.promo
  if (storeOnly) {
    const a = orig != null ? orig : promo
    const b = promo != null ? promo : orig
    return `買場 ${money(a)} · 買場 ${money(b)}`
  }
  return `買場 ${money(orig)} · 線上 ${money(promo)}`
}
