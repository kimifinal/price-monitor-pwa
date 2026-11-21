import { describe, it, expect } from 'vitest'
import { zheOf, sectionHeader, priceLine } from '../../src/lib/mvm.js'
import { loadMvmCatalog } from '../../src/lib/mvm.js'

// #49 (案 B) — the two NEW pure helpers the warm MVM 檔期 view renders through,
// plus the card's last-line helper. Everything the warm card/catalog shows
// (約X折, 到期日, 剩K天, the 買場/線上 line) is deciderd HERE so the components
// stay pure renderers: no number is re-derived in a template.
//
// sectionHeader takes an injectable refDate so a test can pin "today" without
// waiting a real day; the UI passes none and gets the live clock.

describe('zheOf — 約X折 個位, null-safe', () => {
  it('rounds promo/orig to a whole 折 (the mockup examples)', () => {
    expect(zheOf({ orig: 1000, promo: 121 })).toBe(1) // 金冠 1 折
    expect(zheOf({ orig: 349, promo: 329 })).toBe(9) // 王品 9 折
    expect(zheOf({ orig: 1149, promo: 919 })).toBe(8) // 五月花 8 折
    expect(zheOf({ orig: 1899, promo: 1519 })).toBe(8)
    expect(zheOf({ orig: 449, promo: 359 })).toBe(8) // GLICO 8 折
  })

  it('a full-price promo reads 10 折, a deeper-than-listed keeps its value', () => {
    expect(zheOf({ orig: 1000, promo: 1000 })).toBe(10)
    expect(zheOf({ orig: 100, promo: 150 })).toBe(15) // no clamp by design
  })

  it('returns null when orig/promo is missing or ≤ 0 (card then shows N/A)', () => {
    expect(zheOf({ orig: 1000 })).toBeNull() // promo missing
    expect(zheOf({ promo: 121 })).toBeNull() // orig missing
    expect(zheOf({ orig: 0, promo: 121 })).toBeNull()
    expect(zheOf({ orig: 1000, promo: 0 })).toBeNull()
    expect(zheOf({ orig: -5, promo: 10 })).toBeNull()
    expect(zheOf({ orig: null, promo: 100 })).toBeNull()
  })

  it('is null-safe against a non-object / non-numeric figure', () => {
    expect(zheOf(null)).toBeNull()
    expect(zheOf('x')).toBeNull()
    expect(zheOf({})).toBeNull()
    expect(zheOf({ orig: NaN, promo: 500 })).toBeNull() // NaN is not a positive number
  })
})

describe('sectionHeader — N筆 · 檔期名 · 到 MM/DD · 剩 K天', () => {
  const w1 = loadMvmCatalog().tabs[1] // 優惠期間, period 2026/10/26 ~ 11/22, 62 products

  it('prefers the integer n_products, parses 到 MM/DD, and counts days to the injected today', () => {
    const h = sectionHeader(w1, new Date(2026, 10, 20))
    expect(h.count).toBe('66 筆') // n_products is the authoritative 66
    expect(h.label).toBe('優惠期間')
    expect(h.end).toBe('11/22')
    expect(h.daysLeft).toBe(2) // 11/22 − 11/20
    expect(h.text).toBe('66 筆 · 優惠期間 · 到 11/22 · 剩 2 天')
  })

  it('clamps daysLeft at 0 for a 檔期 already past today', () => {
    const h = sectionHeader(w1, new Date(2026, 11, 5)) // 11/27 ref -> 11/22 is past
    expect(h.daysLeft).toBe(0)
    expect(h.text).toBe('66 筆 · 優惠期間 · 到 11/22 · 剩 0 天')
  })

  it('zero-pads MM/DD and resolves a bare M/D end against the start year', () => {
    const h = sectionHeader({ label: '線上專屬', period: '2026/11/27 ~ 12/06', n_products: 17 }, new Date(2026, 10, 20))
    expect(h.end).toBe('12/06')
    expect(h.daysLeft).toBe(16) // 12/06 − 11/20 = 16 (rest of Nov + 6)
  })

  it('a note-count 檔期 (no integer) falls back to the items actually listed', () => {
    const h = sectionHeader(
      { label: '平日限定', period: '2026/10/26 ~ 11/20', n_products: '~10 (已 於 前 次 抓 取)', products: [] },
      new Date(2026, 10, 20),
    )
    expect(h.count).toBe('N/A') // neither an integer nor a listed item -> N/A (gate 19, not "—")
    expect(h.end).toBe('11/20')
    expect(h.daysLeft).toBe(0)
  })

  it('a listed count is used when n_products is not a real integer', () => {
    const h = sectionHeader(
      { label: 'x', period: '2026/01/01 ~ 01/10', n_products: '~5', products: [{ sku: 1 }, { sku: 2 }] },
      new Date(2026, 0, 1),
    )
    expect(h.count).toBe('2 筆')
  })

  it('a non-date period ("敬請期待") yields end "N/A" and omits the 剩-clause', () => {
    const h = sectionHeader({ label: '網購星期一', period: '敬請期待', n_products: 0, products: [] })
    expect(h.end).toBe('N/A')
    expect(h.daysLeft).toBeNull()
    expect(h.text).toBe('N/A · 網購星期一 · 到 N/A')
    expect(h.text).not.toContain('剩')
  })

  it('is null-safe on a missing / non-object tab', () => {
    const h = sectionHeader(null, new Date(2026, 0, 1))
    expect(h.count).toBe('N/A')
    expect(h.label).toBe('N/A')
    expect(h.end).toBe('N/A')
    expect(h.daysLeft).toBeNull()
  })
})

describe('priceLine — 買場/線上 card last line, null-safe (no "—")', () => {
  it('an online-eligible item reads 買場 $原價 · 線上 $促價', () => {
    expect(priceLine({ orig: 1149, promo: 919, type: 'online_only' })).toBe('買場 $1,149 · 線上 $919')
    expect(priceLine({ orig: 1000, promo: 121, type: 'online_only' })).toBe('買場 $1,000 · 線上 $121')
    // a typeless item on an online 檔期 is treated as online-eligible
    expect(priceLine({ orig: 31999, promo: 25599, type: null }, 'online_only')).toBe('買場 $31,999 · 線上 $25,599')
  })

  it('a store-only item reads 買場 買場 (no 線上 price to compare)', () => {
    expect(priceLine({ orig: 449, promo: 359, type: 'store_only' })).toBe('買場 $449 · 買場 $359')
    // a typeless item on a store_only 檔期 resolves the same way
    expect(priceLine({ orig: 449, promo: 359, type: null }, 'store_only')).toBe('買場 $449 · 買場 $359')
    // a sub-variant (store_only_weight) still falls to the 買場 form
    expect(priceLine({ orig: 299, promo: 239, type: 'store_only_weight' })).toBe('買場 $299 · 買場 $239')
  })

  it('stores the 買場 figure as the 原價 and 線上 as the 促價 with TWD grouping', () => {
    expect(priceLine({ orig: 25599, promo: 20769, type: null }, 'online_only')).toBe('買場 $25,599 · 線上 $20,769')
  })

  it('reads "N/A" (never "—") for a missing figure and is null-safe', () => {
    expect(priceLine({ orig: null, promo: 919, type: 'online_only' })).toBe('買場 N/A · 線上 $919')
    expect(priceLine({ orig: 1000, promo: null, type: 'online_only' })).toBe('買場 $1,000 · 線上 N/A')
    expect(priceLine(null)).toBe('買場 N/A · 線上 N/A')
    expect(priceLine({})).toBe('買場 N/A · 線上 N/A')
    // none of the forms leaks an em/en dash
    expect(priceLine(null)).not.toContain('—')
    expect(priceLine({})).not.toContain('—')
  })
})
