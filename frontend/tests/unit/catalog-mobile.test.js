import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CatalogMobile from '../../src/components/mobile/CatalogMobile.vue'
import CatalogProductCard from '../../src/components/mobile/CatalogProductCard.vue'
import {
  loadCatalog,
  isOnlineOnly,
  filterByMode,
  catalogStats,
  countBarText,
  zheOfCatalog,
  catalogPriceLine,
  paginate,
  hasMore,
} from '../../src/lib/catalog.js'

// #50 — the 全部商品 全庫 catalog: the 賣場/線上 sliding toggle + the 10,049-item
// list. The pure helpers (lib/catalog.js) decide every number the view renders,
// so the components stay pure renderers. This file pins the helpers AND mounts
// CatalogMobile over a small fixture so a test never iterates the full 全庫.

// ---------------------------------------------------------------------------
// A small fixture catalog (10 items): 6 賣場 (store) + 4 網路獨家 (online_only),
// two of the store items carry a 促價 below their 原價 (a discount).
// ---------------------------------------------------------------------------
const mk = (o) => ({
  sku: o.sku,
  name: o.name || '品項',
  price: o.price,
  basePrice: o.basePrice,
  discount: o.discount || 0,
  online_only: o.online_only || false,
  stock: o.stock || 'inStock',
})

const FIXTURE = [
  mk({ sku: 's1', price: 100, basePrice: 100 }),
  mk({ sku: 's2', price: 80, basePrice: 100, discount: 20 }), // 2 折? no: 0.8 → 8 折
  mk({ sku: 's3', price: 50, basePrice: 50 }),
  mk({ sku: 's4', price: 121, basePrice: 1000, discount: 879 }), // 1 折
  mk({ sku: 's5', price: 349, basePrice: 439, discount: 90 }), // 8 折
  mk({ sku: 's6', price: 200, basePrice: 200 }),
  mk({ sku: 'o1', price: 499, basePrice: 499, online_only: true }),
  mk({ sku: 'o2', price: 11199, basePrice: 13999, discount: 2800, online_only: true }),
  mk({ sku: 'o3', price: 49, basePrice: 49, online_only: true }),
  mk({ sku: 'o4', price: 99, basePrice: 99, online_only: true }),
]

describe('loadCatalog — the baked 全庫 (offline, null-safe)', () => {
  it('returns the full 10,049-item catalog as an array', () => {
    const c = loadCatalog()
    expect(Array.isArray(c)).toBe(true)
    expect(c).toHaveLength(10049)
  })

  it('normalizes a non-object row to a null-safe record (never crashes a render)', () => {
    // isOnlineOnly / filterByMode / catalogStats tolerate junk, so a bad row
    // can't poison a count.
    expect(isOnlineOnly(null)).toBeFalsy() // null-safe: a non-object is "not online"
    expect(isOnlineOnly({})).toBe(false)
    expect(filterByMode(null, 'store')).toEqual([])
    expect(catalogStats(null)).toEqual({ total: 0, store: 0, onlineOnly: 0 })
  })
})

describe('isOnlineOnly + filterByMode — 賣場/線上 split', () => {
  it('isOnlineOnly flags only the 網路獨家 items', () => {
    expect(isOnlineOnly(FIXTURE[6])).toBe(true)
    expect(isOnlineOnly(FIXTURE[0])).toBe(false)
    expect(isOnlineOnly({ online_only: 'yes' })).toBe(false) // strict === true
  })

  it('store mode hides the 網路獨家 items; online mode shows the whole 全庫', () => {
    const store = filterByMode(FIXTURE, 'store')
    const online = filterByMode(FIXTURE, 'online')
    expect(store).toHaveLength(6) // 6 賣場
    expect(store.every((p) => !isOnlineOnly(p))).toBe(true)
    expect(online).toHaveLength(10) // 全庫
    expect(online.filter(isOnlineOnly)).toHaveLength(4)
  })
})

describe('catalogStats — total / store / onlineOnly', () => {
  it('splits the 全庫 into store + onlineOnly', () => {
    expect(catalogStats(FIXTURE)).toEqual({ total: 10, store: 6, onlineOnly: 4 })
  })

  it('is null-safe (a non-array yields all zeros)', () => {
    expect(catalogStats(null)).toEqual({ total: 0, store: 0, onlineOnly: 0 })
  })
})

describe('countBarText — the count bar under the toggle', () => {
  it('store mode: "6 筆賣場可購 · 4 項線上 專 屬已隱藏"', () => {
    expect(countBarText(FIXTURE, 'store')).toBe('6 筆賣場可購 · 4 項線上 專 屬已隱藏')
  })

  it('online mode: "10 筆全庫 · 含 4 項線上 專 屬"', () => {
    expect(countBarText(FIXTURE, 'online')).toBe('10 筆全庫 · 含 4 項線上 專 屬')
  })

  it('a zero-count mode reads "N/A" (never "—")', () => {
    expect(countBarText([], 'store')).toBe('N/A')
    expect(countBarText([], 'online')).toBe('N/A')
  })
})

describe('zheOfCatalog — 約 X 折 from price→basePrice, null-safe', () => {
  it('rounds price/base to a whole 折 (the spec examples)', () => {
    expect(zheOfCatalog({ price: 121, basePrice: 1000 })).toBe(1) // 1 折
    expect(zheOfCatalog({ price: 5199, basePrice: 6899 })).toBe(8)
    expect(zheOfCatalog({ price: 349, basePrice: 439 })).toBe(8)
  })

  it('returns null for null / missing / non-positive figures', () => {
    expect(zheOfCatalog(null)).toBeNull()
    expect(zheOfCatalog({})).toBeNull()
    expect(zheOfCatalog({ price: null, basePrice: 100 })).toBeNull()
    expect(zheOfCatalog({ price: 100, basePrice: null })).toBeNull()
    expect(zheOfCatalog({ price: 100, basePrice: 0 })).toBeNull()
  })

  it('returns null when there is no discount (price >= base)', () => {
    expect(zheOfCatalog({ price: 100, basePrice: 100 })).toBeNull()
    expect(zheOfCatalog({ price: 120, basePrice: 100 })).toBeNull()
  })
})

describe('catalogPriceLine — 賣場 / 線上 / two-figure variants', () => {
  it('store mode shows "賣場 $price" (the item price)', () => {
    expect(catalogPriceLine({ price: 100, basePrice: 100, online_only: false }, 'store')).toBe('賣場 $100')
    expect(catalogPriceLine({ price: 80, basePrice: 100, discount: 20, online_only: false }, 'store')).toBe('賣場 $80')
  })

  it('online mode, a 網路獨家 item, shows "線上 $price" (its only price)', () => {
    expect(catalogPriceLine({ price: 499, basePrice: 499, online_only: true }, 'online')).toBe('線上 $499')
  })

  it('online mode, a discounted store item, shows "賣場 $base · 線上 $price"', () => {
    expect(catalogPriceLine({ price: 80, basePrice: 100, discount: 20, online_only: false }, 'online')).toBe('賣場 $100 · 線上 $80')
  })

  it('online mode, a non-discounted store item, shows just "線上 $price"', () => {
    expect(catalogPriceLine({ price: 100, basePrice: 100, online_only: false }, 'online')).toBe('線上 $100')
  })

  it('a missing figure reads "N/A" (never "—")', () => {
    expect(catalogPriceLine({ price: null, basePrice: null, online_only: false }, 'store')).toBe('賣場 N/A')
  })
})

describe('paginate + hasMore — the 顯示更多 windowing', () => {
  it('slices a window and reports whether more remain', () => {
    const list = Array.from({ length: 12 }, (_, i) => i)
    expect(paginate(list, 0, 5)).toEqual([0, 1, 2, 3, 4])
    expect(paginate(list, 1, 5)).toEqual([5, 6, 7, 8, 9])
    expect(paginate(list, 2, 5)).toEqual([10, 11])
    expect(hasMore(list, 0, 5)).toBe(true)
    expect(hasMore(list, 2, 5)).toBe(false) // 12 not > (2+1)*5
    expect(hasMore(null, 0, 5)).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Mounting CatalogMobile over a small fixture (never the full 全庫 in a test).
// ---------------------------------------------------------------------------
describe('CatalogMobile.vue — the 全部 全庫 view', () => {
  it('mounts in 賣場 mode: 6 store cards, the count bar, and the 賣場 toggle active', () => {
    const w = mount(CatalogMobile, { props: { catalog: FIXTURE } })
    // default mode = store → the 4 網路獨家 items are hidden
    expect(w.findAll('.m-cat-card')).toHaveLength(6)
    expect(w.find('[data-seg="store"]').classes()).toContain('is-active')
    expect(w.find('[data-seg="online"]').classes()).not.toContain('is-active')
    expect(w.find('[data-cat-count]').text()).toBe('6 筆賣場可購 · 4 項線上 專 屬已隱藏')
  })

  it('the 賣場/線上 toggle flips the mode, the count bar, and the rendered set', async () => {
    const w = mount(CatalogMobile, { props: { catalog: FIXTURE } })
    expect(w.findAll('.m-cat-card')).toHaveLength(6)
    await w.find('[data-seg="online"]').trigger('click')
    // online mode shows the whole 全庫 and updates the count bar
    expect(w.find('[data-seg="online"]').classes()).toContain('is-active')
    expect(w.find('[data-seg="store"]').classes()).not.toContain('is-active')
    expect(w.findAll('.m-cat-card')).toHaveLength(10)
    expect(w.find('[data-cat-count]').text()).toBe('10 筆全庫 · 含 4 項線上 專 屬')
    // a 網路獨家 card now carries the orange 僅限線上 badge in online mode
    expect(w.find('.m-cat-badge-online').exists()).toBe(true)
  })

  it('a 網路獨家 card shows no 僅限線上 badge while in 賣場 mode', () => {
    const w = mount(CatalogMobile, { props: { catalog: FIXTURE } })
    expect(w.find('.m-cat-badge-online').exists()).toBe(false)
  })

  it('a discounted store item renders a 省 badge and a 約 X 折 badge', () => {
    // mount the single card so the badge assertions are unambiguous (a store
    // item with 促價 121 below 原價 1000 → 1 折, 省 $879)
    const s4 = { sku: 's4', name: '品項', price: 121, basePrice: 1000, discount: 879, online_only: false, stock: 'inStock' }
    const w = mount(CatalogProductCard, { props: { product: s4, mode: 'store' } })
    expect(w.find('.m-cat-badge-save').text()).toBe('省 $879')
    expect(w.find('.m-cat-badge-zhe').text()).toBe('約 1 折')
  })

  it('"顯示更多" paginates 50-at-a-time (fixture page size 3): 3 → 6, then stops', async () => {
    const w = mount(CatalogMobile, { props: { catalog: FIXTURE, pageSize: 3 } })
    // store mode = 6 items; first page of 3, with a 顯示更多 button
    expect(w.findAll('.m-cat-card')).toHaveLength(3)
    expect(w.find('[data-cat-more]').exists()).toBe(true)
    // one click reveals the remaining 3 (6 total) and the button disappears
    await w.find('[data-cat-more]').trigger('click')
    expect(w.findAll('.m-cat-card')).toHaveLength(6)
    expect(w.find('[data-cat-more]').exists()).toBe(false)
  })

  it('a round white 篩選 button is present and toggles aria-pressed', async () => {
    const w = mount(CatalogMobile, { props: { catalog: FIXTURE } })
    const f = w.find('[data-cat-filter]')
    expect(f.exists()).toBe(true)
    expect(f.attributes('aria-label')).toBe('篩選')
    expect(f.attributes('aria-pressed')).toBe('false')
    await f.trigger('click')
    expect(w.find('[data-cat-filter]').attributes('aria-pressed')).toBe('true')
  })
})

describe('CatalogProductCard.vue — a single warm card', () => {
  it('renders the name, the main price, and the price line', () => {
    const w = mount(CatalogProductCard, {
      props: { product: { sku: 'x', name: '測試品項', price: 100, basePrice: 100, discount: 0, online_only: false, stock: 'inStock' }, mode: 'store' },
    })
    expect(w.find('.m-cat-name').text()).toBe('測試品項')
    expect(w.find('.m-cat-promo').text()).toBe('$100')
    expect(w.find('.m-cat-line').text()).toBe('賣場 $100')
  })

  it('shows the struck original price only when it differs from the main price', () => {
    const noOrig = mount(CatalogProductCard, {
      props: { product: { sku: 'x', name: 'n', price: 100, basePrice: 100, discount: 0, online_only: false, stock: 'inStock' }, mode: 'store' },
    })
    expect(noOrig.find('.m-cat-orig').exists()).toBe(false)
    const discounted = mount(CatalogProductCard, {
      props: { product: { sku: 'x', name: 'n', price: 80, basePrice: 100, discount: 20, online_only: false, stock: 'inStock' }, mode: 'online' },
    })
    expect(discounted.find('.m-cat-orig').exists()).toBe(true)
    expect(discounted.find('.m-cat-orig').text()).toBe('$100')
  })

  it('a discounted item in online mode takes the blue price tint', () => {
    const w = mount(CatalogProductCard, {
      props: { product: { sku: 'x', name: 'n', price: 80, basePrice: 100, discount: 20, online_only: false, stock: 'inStock' }, mode: 'online' },
    })
    expect(w.find('.m-cat-promo').classes()).toContain('is-blue')
    // store mode keeps the red price (no blue tint)
    const store = mount(CatalogProductCard, {
      props: { product: { sku: 'x', name: 'n', price: 80, basePrice: 100, discount: 20, online_only: false, stock: 'inStock' }, mode: 'store' },
    })
    expect(store.find('.m-cat-promo').classes()).not.toContain('is-blue')
  })

  it('is null-safe: a null product renders without crashing and reads "N/A"', () => {
    const w = mount(CatalogProductCard, { props: { product: null, mode: 'store' } })
    expect(w.find('.m-cat-promo').text()).toBe('N/A')
    expect(w.find('.m-cat-line').text()).toBe('賣場 N/A')
  })
})
