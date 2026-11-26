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
 * these two baked snapshots (no network — offline-safe); the 規格摘要 (吸力 /
 * 重量 / 使用時間 / 濾網) is a PLACEHOLDER because the baked catalog carries no
 * spec fields (verified: every item has exactly sku/name/price/basePrice/
 * discount/online_only/stock — see specList below). The 到官網 URL is a best-
 * effort 好市多 TW search link built from the item (no per-item URL in the data).
 *
 * TWD grouping reuses formatTWD (the TWD SSOT, issue #25); the "約 X 折" 個位
 * reuses zheOfCatalog and the "省 $X" text reuses saveText from catalog.js, so
 * the discount math stays single-sourced across the whole mobile shell.
 */
import { formatTWD } from './format.js'
import { zheOfCatalog, saveText } from './catalog.js'

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

// The 規格摘要 four fields the mockup shows. The baked catalog carries NONE of
// them (verified: every item has exactly sku/name/price/basePrice/discount/
// online_only/stock), so each is an honest PLACEHOLDER awaiting a backend 規格
// column. The value reads "待補" (never an em-dash — gate 19) and the section
// carries an explicit "後端補欄" note so it is clearly a placeholder, not real
// data. A future pass fills `value` from a real 規格 column keyed by sku.
export const SPEC_FIELDS = [
  { key: 'suction', label: '吸力' },
  { key: 'weight', label: '重量' },
  { key: 'runtime', label: '使用時間' },
  { key: 'filter', label: '濾網' },
]

/**
 * The 規格摘要 grid. Each field resolves `specs[key]` (a real 規格 column when a
 * backend adds one) and otherwise falls back to the "待補" placeholder. Pure +
 * null-safe; never emits an em/en dash.
 * @param {object} p the item (may carry a future `specs` object)
 * @returns {Array<{key:string,label:string,value:string,placeholder:boolean}>}
 */
export function specList(p) {
  const specs = (p && typeof p === 'object' && p.specs && typeof p.specs === 'object') ? p.specs : {}
  return SPEC_FIELDS.map((f) => {
    const raw = specs[f.key]
    const has = raw != null && raw !== '' && raw !== 'N/A'
    return {
      key: f.key,
      label: f.label,
      value: has ? String(raw) : '待補',
      placeholder: !has,
    }
  })
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
 * @param {object} [ctx]    { endDate?: string } — the active 檔期 range chip
 * @returns {{
 *   sku: string, name: string,
 *   store: { now:number|null, orig:number|null, note:string },
 *   online: { now:number|null, orig:number|null, available:boolean,
 *             onlineOnly:boolean, note:string },
 *   save: number|null, zhe:number|null, endDate:string,
 *   specs: Array, webUrl: string
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
    specs: specList(item),
    webUrl: costcoUrl(item),
  }
}

// A "$"-prefixed TWD figure for display (matches the mockup's "$5,199"), or
// "N/A" for a missing figure (gate 19). Exported so a component renders money
// through ONE helper instead of re-deriving grouping.
export function money(n) {
  return n == null ? 'N/A' : '$' + formatTWD(n)
}
