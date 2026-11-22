import { describe, it, expect } from 'vitest'
import {
  loadMvmCatalog,
  defaultActiveTab,
  discountPct,
  discountTier,
  tabCountText,
  isEmptyTab,
  productBadge,
  sortProducts,
  filterByCategory,
  categoriesOf,
} from '../../src/lib/mvm.js'

// MVM 檔期目錄 — the baked snapshot + its pure render helpers. Everything the
// UI shows (discount %, colour tier, tab count, badge, ordering) is deciderd
// HERE so the components stay pure renderers and no number is re-derived in a
// template. TWD money has no sub-unit, so a discount is a 1-decimal figure.
describe('lib/mvm.js — baked snapshot structure', () => {
  it('exposes 6 檔期, 3 price types, and a crawl date (offline, no fetch)', () => {
    const c = loadMvmCatalog()
    expect(c.tabs.length).toBe(7) // Kimi 11-22: 黑色購物週 added → 7 tabs
    expect(Object.keys(c.priceTypes)).toEqual(
      expect.arrayContaining(['online_only', 'store_online_diff', 'store_only']),
    )
    expect(Object.keys(c.priceTypes).length).toBe(3)
    expect(typeof c.sourceDate).toBe('string')
    // every 檔期 is an object with a tab_id + a products array (possibly empty)
    for (const t of c.tabs) {
      expect(typeof t.tab_id).toBe('string')
      expect(Array.isArray(t.products)).toBe(true)
    }
  })
})

describe('discountPct — null-safe, one decimal (no .00, no toFixed(2))', () => {
  it('computes discount/orig to one decimal', () => {
    expect(discountPct({ orig: 1000, discount: 250 })).toBe(25)
    expect(discountPct({ orig: 1149, discount: 230 })).toBe(20)
    // a genuine zero discount is valid (0%), distinct from "cannot compute"
    expect(discountPct({ orig: 1000, discount: 0 })).toBe(0)
  })
  it('returns null when orig/promo/discount is missing (card then shows N/A)', () => {
    expect(discountPct({ orig: 1000, discount: null })).toBeNull()
    expect(discountPct({ discount: 230 })).toBeNull()
    expect(discountPct({ orig: 0, discount: 50 })).toBeNull()
    expect(discountPct({ orig: -5, discount: 10 })).toBeNull()
    expect(discountPct(null)).toBeNull()
    expect(discountPct('not-an-object')).toBeNull()
  })
})

describe('discountTier — colour breakpoints (>=25 high, 15-25 mid, <15 low)', () => {
  it('maps percent to the token tier', () => {
    expect(discountTier(31)).toBe('high')
    expect(discountTier(25)).toBe('high')
    expect(discountTier(20)).toBe('mid')
    expect(discountTier(15)).toBe('mid')
    expect(discountTier(14.9)).toBe('low')
    expect(discountTier(0)).toBe('low')
    // a missing figure has no colour to paint -> low/muted
    expect(discountTier(null)).toBe('low')
    expect(discountTier(Number.NaN)).toBe('low')
  })
})

describe('tabCountText — a real integer renders, anything else is N/A (gate 19)', () => {
  it('renders positive integer counts', () => {
    expect(tabCountText({ n_products: 66 })).toBe('66')
    expect(tabCountText({ n_products: 17 })).toBe('17')
  })
  it('renders N/A for 0, a non-integer note, or a missing count', () => {
    expect(tabCountText({ n_products: 0 })).toBe('N/A')
    expect(tabCountText({ n_products: '~10 (已 於 前 次 抓 取)' })).toBe('N/A')
    expect(tabCountText({})).toBe('N/A')
    expect(tabCountText(null)).toBe('N/A')
  })
})

describe('isEmptyTab / defaultActiveTab', () => {
  it('a 檔期 with no products is empty', () => {
    expect(isEmptyTab({ products: [] })).toBe(true)
    expect(isEmptyTab({})).toBe(true)
    expect(isEmptyTab({ products: [{ sku: 1 }] })).toBe(false)
  })
  it('defaults to the first tab that carries products, not an empty one', () => {
    const tabs = [
      { tab_id: 'empty', products: [] },
      { tab_id: 'full', products: [{ sku: 1 }] },
    ]
    expect(defaultActiveTab(tabs, '')).toBe('full')
  })
  it('honours a valid initialTab', () => {
    const tabs = [
      { tab_id: 'a', products: [{ sku: 1 }] },
      { tab_id: 'b', products: [{ sku: 2 }] },
    ]
    expect(defaultActiveTab(tabs, 'b')).toBe('b')
  })
  it('falls back when initialTab names no real tab, and to "" when no tabs', () => {
    const tabs = [
      { tab_id: 'a', products: [] },
      { tab_id: 'b', products: [] },
    ]
    expect(defaultActiveTab(tabs, 'no-such-tab')).toBe('a')
    expect(defaultActiveTab([], 'anything')).toBe('')
    expect(defaultActiveTab(null, '')).toBe('')
  })
})

describe('productBadge — type lookup with sub-variant fallback (gate 64 base)', () => {
  const priceTypes = {
    online_only: { label: '線上專屬', meaning: 'only online' },
    store_online_diff: { label: '賣場+線上', meaning: 'diff' },
    store_only: { label: '賣場獨家', meaning: 'store only' },
  }
  it('resolves a known type to its label + meaning', () => {
    expect(productBadge({ type: 'online_only' }, priceTypes)).toEqual({
      key: 'online_only',
      label: '線上專屬',
      meaning: 'only online',
    })
  })
  it('falls a sub-variant back to its base (store_only_weight -> store_only)', () => {
    const b = productBadge({ type: 'store_only_weight' }, priceTypes)
    expect(b.key).toBe('store_only')
    expect(b.label).toBe('賣場獨家')
  })
  it('defaults an unknown / missing type to store_only', () => {
    expect(productBadge({ type: 'mystery' }, priceTypes).key).toBe('store_only')
    expect(productBadge({}, priceTypes).key).toBe('store_only')
  })
  it('degrades a missing price_types map to a key-only badge', () => {
    expect(productBadge({ type: 'store_only' }, {})).toEqual({
      key: 'store_only',
      label: 'store_only',
      meaning: '',
    })
  })
})

describe('sortProducts + filterByCategory + categoriesOf', () => {
  // ASCII categories/names so ordering is deterministic regardless of the
  // runtime's default locale (CJK localeCompare order is not stable across
  // runtimes; only the *invariants* below are asserted).
  const products = [
    { sku: 1, cat: 'z', name: 'y', orig: 100, discount: 10, promo: 90 },
    { sku: 2, cat: 'a', name: 'x', orig: 1000, discount: 900, promo: 100 },
    { sku: 3, cat: 'm', name: 'w', orig: 0, discount: null, promo: 50 },
  ]
  it('sorts by deepest discount first by default (null discounts sink to last)', () => {
    // p2 = 90%, p1 = 10%, p3 = no computable discount -> 0 -> last
    expect(sortProducts(products, 'discount').map((p) => p.sku)).toEqual([2, 1, 3])
  })
  it('sorts by category ascending (grouped), then name within a group', () => {
    // 'a' < 'm' < 'z' in every locale -> p2, p3, p1
    expect(sortProducts(products, 'category').map((p) => p.sku)).toEqual([2, 3, 1])
  })
  it('sorts by price = highest promo first', () => {
    expect(sortProducts(products, 'price').map((p) => p.promo)).toEqual([100, 90, 50])
  })
  it('does not mutate the input', () => {
    const before = JSON.stringify(products)
    sortProducts(products, 'discount')
    sortProducts(products, 'category')
    expect(JSON.stringify(products)).toBe(before)
  })
  it('"all" keeps everything, a known category filters, an unknown one keeps none', () => {
    expect(filterByCategory(products, 'all').length).toBe(3)
    expect(filterByCategory(products, 'a').map((p) => p.sku)).toEqual([2])
    expect(filterByCategory(products, 'nope')).toEqual([])
  })
  it('lists distinct categories sorted ascending', () => {
    expect(categoriesOf(products)).toEqual(['a', 'm', 'z'])
    expect(categoriesOf([])).toEqual([])
  })
})
