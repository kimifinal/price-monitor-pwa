/**
 * detail.js — the 商品詳情頁 (#53) pure render model.
 *
 * The detail view (ProductDetail.vue) is a PURE renderer: every figure, badge,
 * note, and the 到官網 URL it shows is decided here, never re-derived in the
 * template. It is null-safe the way the rest of the warm mobile helpers are
 * (gate 19: a missing figure reads "N/A", NEVER an em/en dash "—" / "–", and
 * never a bogus $0).
 *
 * TWO item shapes flow into it, so the model normalizes BOTH:
 *   • catalog.json item (#50 全庫):  { sku, name, price, basePrice, discount,
 *     online_only, stock }
 *   • mvm.json item (#49 特價 檔期):  { sku, name, orig, promo, discount, type,
 *     cat, note }
 * A catalog 現價 is `price` (its 原價 is `basePrice`); an MVM 現價 is `promo`
 * (its 原價 is `orig`). The normalizer reads `price ?? promo` / `basePrice ??
 * orig`, so a detail page reached from EITHER the 全部 全庫 or the 特價 檔期 view
 * shows the same 賣場 / 線上 structure with the right figures.
 *
 * Data the issue names: 價格 / 原價 / 省額 / 折扣 / 檔期 / 通路 / 缺貨 come from
 * these two baked snapshots (no network — offline-safe). The 特價紀錄 (#55) 賣場
 * row is driven by the sku's costco-history record (a real price series →
 * sparkline + verdict + 特價幾次 / 一年最低 / 現價 / 省 / 到), while the 線上 row
 * shows the 當前線上價 + a placeholder (no series yet, #56 — never a faked curve).
 * The 到官網 URL is a best-effort 好市多 TW search link built from the item
 * (no per-item URL in the data).
 *
 * TWD grouping reuses formatTWD (the TWD SSOT, issue #25); the "約 X 折" 個位
 * reuses zheOfCatalog and the "省 $X" text reuses saveText from catalog.js, so
 * the discount math stays single-sourced across the whole mobile shell.
 */
import { formatTWD } from './format.js'
import { zheOfCatalog, saveText } from './catalog.js'
// #55 特價紀錄 reuses the verdict SSOT + offline sparkline from monitor.js so the
// 賣場 row never re-derives a verdict or a sparkline of its own.
import { priceVerdict, sparkPath } from './monitor.js'

/** Coerce a value to a finite number, or null (gate 19: null -> "N/A"). */
function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** Read the first present, finite figure from a list of candidate keys. */
function firstNum(p, keys) {
  for (const k of keys) {
    const n = num(p[k])
    if (n != null) return n
  }
  return null
}

/**
 * The 現價 (promo) + 原價 (original) for an item, shape-agnostic.
 *   catalog → price / basePrice ;  MVM → promo / orig.
 * @param {object} p
 * @returns {{now:number|null, orig:number|null}}
 */
export function priceOf(p) {
  const item = p && typeof p === 'object' ? p : {}
  return { now: firstNum(item, ['price', 'promo']), orig: firstNum(item, ['basePrice', 'orig']) }
}

/** Whether the item is a 網路獨家 (online-exclusive) item, either shape. */
export function isOnlineOnly(p) {
  if (!p || typeof p !== 'object') return false
  if (p.online_only === true) return true
  return /^online_only/.test(String(p.type || ''))
}

/**
 * Whether the item is in stock. The baked catalog carries a `stock` string
 * ("inStock" / "outOfStock" / "N/A"); MVM items have no stock field, so a
 * missing field reads as available (true) — an unknown 缺貨 is not asserted as
 * out-of-stock. Pure + null-safe.
 * @param {object} p
 * @returns {boolean}
 */
export function isAvailable(p) {
  if (!p || typeof p !== 'object') return true
  const s = p.stock
  if (s == null || s === 'N/A') return true
  return s === 'inStock'
}

/**
 * The 省額 for an item: its carried `discount` when positive, else derived from
 * 原價 − 現價 when both exist and 原價 > 現價, else null (no 省 chip). Pure +
 * null-safe.
 * @param {object} p
 * @returns {number|null}
 */
export function saveOf(p) {
  const item = p && typeof p === 'object' ? p : {}
  const d = num(item.discount)
  if (d != null && d > 0) return d
  const { now, orig } = priceOf(item)
  if (now != null && orig != null && orig > now) return orig - now
  return null
}

/**
 * The "約 X 折" 個位 for an item, reusing zheOfCatalog (price→basePrice 個位,
 * the catalog SSOT). We feed it a synthetic {price, basePrice} built from the
 * item's 現價 / 原價 so the SAME 折 math serves both shapes. null (missing / ≤0 /
 * no discount) hides the chip.
 * @param {object} p
 * @returns {number|null}
 */
export function zheOfItem(p) {
  const { now, orig } = priceOf(p && typeof p === 'object' ? p : {})
  return zheOfCatalog({ price: now, basePrice: orig })
}

/**
 * The "省 $X" text, reusing saveText (the TWD-grouped 省 string) so the 省 badge
 * reads identically to the catalog card. '' when there is no positive 省.
 * @param {object} p
 * @returns {string}
 */
export function saveTextOf(p) {
  const save = saveOf(p)
  return save == null ? '' : saveText({ discount: save })
}

/**
 * The 到 MM/DD 到期日 chip text for the active 檔期, reused verbatim from the
 * MVM range string. A blank / "N/A" / "敬請期待" 檔期 hides the chip (a no-date
 * 檔期 shows nothing extra), mirroring MvmMobileProductCard's endDateShown.
 * @param {string} endDate
 * @returns {string}
 */
export function endDateChip(endDate) {
  const s = String(endDate || '').trim()
  if (!s || s === 'N/A' || s === '敬請期待') return ''
  return s.includes('~') ? s : `到 ${s}`
}

// --- 特價紀錄 (#55) ----------------------------------------------------------
// Replaces the old 規格摘要 placeholder grid. The 賣場 row is driven by the sku's
// costco-history record (a REAL price series), so it renders a sparkline + a
// verdict + 特價幾次 / 一年最低 / 現價 / 省 / 到. The 線上 row has no series yet
// (#56), so it shows the 當前線上價 + an honest "待補" placeholder — and NEVER a
// faked curve. priceVerdict (verdict SSOT) + sparkPath (offline sparkline) +
// money (TWD grouping SSOT) are all reused, so nothing is re-derived here.

// 特價幾次 = the number of downward steps in the price series: each time today's
// observed price is STRICTLY less than the previous observation, the price
// "dropped" once. Pure + null-safe (a malformed series counts 0, never throws).
function countDrops(series) {
  if (!Array.isArray(series)) return 0
  let drops = 0
  for (let i = 1; i < series.length; i++) {
    const a = num(series[i - 1] && series[i - 1].price)
    const b = num(series[i] && series[i].price)
    if (a != null && b != null && b < a) drops++
  }
  return drops
}

// Map a priceVerdict key to a --m-* color token + a clean (emoji-free) label.
// priceVerdict's OWN label carries emoji ("歷史最低 👍" / "較近低點 ▼X%") — gate:
// 把 emoji 移除 — so we REUSE priceVerdict for the verdict CLASSIFICATION but
// re-derive a clean label here. good_deal's label is a function of the dropPct.
const VERDICT_UI = {
  all_time_low: { color: 'var(--m-good)', label: '歷史最低' },
  good_deal: { color: 'var(--m-warm)', label: (pct) => `較近低點 ${Math.round(pct)}%` },
  near_high: { color: 'var(--m-warn)', label: '接近高點' },
  stable: { color: 'var(--m-ink-3)', label: '平穩' },
  unknown: { color: 'var(--m-ink-3)', label: '無歷史' },
}

function verdictUi(key, dropPct) {
  const ui = VERDICT_UI[key] || VERDICT_UI.unknown
  const label = typeof ui.label === 'function' ? ui.label(dropPct || 0) : ui.label
  return { key, label, color: ui.color, dropPct: dropPct || 0 }
}

/**
 * The 特價紀錄 model (#55): a 賣場 row (real price history from the sku's
 * costco-history record) + an 線上 row (當前線上價 + placeholder, NO faked curve).
 * Pure + null-safe — a null / missing / malformed record yields a well-formed
 * "尚無歷史" model, never a throw, undefined, or bogus figure (gate 19).
 *
 * @param {object} p         a catalog OR MVM item (shape-agnostic, like priceOf)
 * @param {object} [record]  the sku's costco-history record (null when offline or
 *                           the sku has no history row)
 * @param {string} [endDate] the active 檔期 period chip text (the MVM tab period;
 *                           '' for catalog items, which carry no 檔期 of their own)
 * @returns {{
 *   hasHistory: boolean,
 *   store: {
 *     hasHistory: boolean, series: Array, spark: string,
 *     verdict: {key:string,label:string,color:string,dropPct:number},
 *     drops: number,
 *     now: number|null, nowText: string,
 *     low: number|null, lowText: string,
 *     save: number|null, saveText: string, end: string
 *   },
 *   online: {
 *     now: number|null, money: string, hasSeries: boolean, note: string
 *   }
 * }}
 */
export function promoRecord(p, record = null, endDate = '') {
  const item = p && typeof p === 'object' ? p : {}
  const { now: onlineNow, orig } = priceOf(item)

  // The 檔期 "到" chip (MVM 檔期 end). Catalog items carry no 檔期, so '' hides it.
  const end = endDateChip(endDate)

  // 線上 row: ONLY the 當前線上價 + an honest placeholder — no series, no curve.
  const online = {
    now: onlineNow,
    money: money(onlineNow),
    hasSeries: false,
    note: '線上歷史序列待補（#56）',
  }

  // No record (offline / sku not tracked) → a 尚無歷史 賣場 row (never a throw).
  if (!record || typeof record !== 'object') {
    return {
      hasHistory: false,
      store: {
        hasHistory: false,
        series: [],
        spark: '',
        verdict: verdictUi('unknown', 0),
        drops: 0,
        now: null,
        nowText: 'N/A',
        low: null,
        lowText: 'N/A',
        save: null,
        saveText: '',
        end,
      },
      online,
    }
  }

  const series = Array.isArray(record.series) ? record.series : []
  const hasHistory = series.length > 0

  // 現價 / 一年最低 / 省 (原價 − 現價) / 特價幾次 — all from the record + item.
  const now = num(record.current)
  const low = num(record.low)
  const save = orig != null && now != null && orig > now ? orig - now : null
  const drops = hasHistory ? countDrops(series) : 0

  // The verdict REUSES priceVerdict (SSOT classification). priceVerdict expects a
  // camelCase metrics shape, so map the record's snake_case fields onto it.
  const metrics = {
    points: record.points != null ? record.points : series.length,
    dropPctFromHigh: record.drop_pct_from_high,
    atAllTimeLow: record.at_all_time_low,
  }
  const v = hasHistory
    ? priceVerdict(metrics)
    : { verdict: 'unknown', label: '無歷史', dropPct: 0 }

  return {
    hasHistory,
    store: {
      hasHistory,
      series,
      // sparkPath draws the offline polyline (or '' when there is nothing to draw).
      spark: hasHistory ? sparkPath(series) : '',
      verdict: verdictUi(v.verdict, v.dropPct),
      drops,
      now,
      nowText: money(now),
      low,
      lowText: money(low),
      save,
      saveText: save != null ? money(save) : '',
      end,
    },
    online,
  }
}

/**
 * The best-effort 到官網看 URL for an item: a 好市多 TW search by product name
 * (the baked data carries no per-item product URL, so a name search is the
 * honest link — it always lands the user in the right 通路). Falls back to a
 * bare search root when the name is missing.
 * @param {object} p
 * @returns {string} an https://www.costco.com.tw URL
 */
export function costcoUrl(p) {
  const name = (p && typeof p === 'object' && p.name) || ''
  const q = encodeURIComponent(String(name || '').trim())
  return `https://www.costco.com.tw/search/?q=${q}`
}

/**
 * The unified detail model ProductDetail.vue renders. Pure + null-safe.
 *
 * @param {object} p        a catalog OR MVM item
 * @param {object} [ctx]    { endDate?: string, historyRecord?: object } — the active
 *                           檔期 range chip + the sku's costco-history record (#55)
 * @returns {{
 *   sku: string, name: string,
 *   store: { now:number|null, orig:number|null, note:string },
 *   online: { now:number|null, orig:number|null, available:boolean,
 *             onlineOnly:boolean, note:string },
 *   save: number|null, zhe:number|null, endDate:string,
 *   promo: object, webUrl: string
 * }}
 */
export function buildDetailModel(p, ctx = {}) {
  const item = p && typeof p === 'object' ? p : {}
  const { now, orig } = priceOf(item)
  const onlineOnly = isOnlineOnly(item)
  const available = isAvailable(item)
  const save = saveOf(item)
  const zhe = zheOfItem(item)

  // 賣場 channel. An 網路獨家 item is not sold in the 賣場, so its 賣場 figure is
  // "不於賣場販售" (N/A) rather than a bogus mirror of the 線上 price.
  const store = onlineOnly
    ? { now: null, orig: null, note: '不於賣場販售（網路獨家）' }
    : { now, orig, note: '會員護照價，以賣場為準' }

  // 線上 channel: shows the item's figure with its availability + 僅限線上 cue.
  // A 缺貨 線上 item reads the mockup's "線上目前缺貨，賣場可能還有"; a 網路獨家
  // in-stock item reads "僅限線上現貨，可官網直購"; a normal in-stock item reads
  // "線上現貨，可官網直購".
  let onlineNote
  if (!available) onlineNote = '線上目前缺貨，賣場可能還有'
  else if (onlineOnly) onlineNote = '僅限線上現貨，可官網直購'
  else onlineNote = '線上現貨，可官網直購'
  const online = { now, orig, available, onlineOnly, note: onlineNote }

  return {
    sku: item.sku != null ? String(item.sku) : 'N/A',
    name: item.name || '未命名品項',
    store,
    online,
    save,
    zhe,
    endDate: endDateChip(ctx.endDate),
    // #55: 特價紀錄 replaces 規格摘要. ctx.historyRecord is the sku's costco-history
    // record (null when offline / not found → "尚無歷史"); ctx.endDate is the MVM
    // 檔期 period chip (catalog items pass none).
    promo: promoRecord(item, ctx.historyRecord, ctx.endDate),
    webUrl: costcoUrl(item),
  }
}

// A "$"-prefixed TWD figure for display (matches the mockup's "$5,199"), or
// "N/A" for a missing figure (gate 19). Exported so a component renders money
// through ONE helper instead of re-deriving grouping.
export function money(n) {
  return n == null ? 'N/A' : '$' + formatTWD(n)
}
