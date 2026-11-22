import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MvmMobileCatalog from '../../src/components/mobile/MvmMobileCatalog.vue'
import MvmMobileProductCard from '../../src/components/mobile/MvmMobileProductCard.vue'
import { loadMvmCatalog, sectionHeader, isPeriodExpired, activePeriods } from '../../src/lib/mvm.js'

// #49 (案 B) — the warm MVM 檔期 view (the "特價" tab) + its product card.
//
// Asserts the behaviours the 檔期 mockup + spec demand: 6 檔 chips on a
// horizontal axis, NO 買場/線上 toggle, the section title in the exact spec form
// `N 筆 · 檔期名 · 到 MM/DD · 剩 K 天`, a full item list of the active 檔期, the
// "約 X 折" badge, and the 買場 $X · 線上 $Y / 買場 $X · 買場 $Y last line.

const c = loadMvmCatalog()
const REF = new Date(2026, 10, 20) // pin "today" to 11/20 for determinism
const mountAt = (props = {}) =>
  mount(MvmMobileCatalog, {
    props: {
      tabs: c.tabs,
      priceTypes: c.priceTypes,
      sourceDate: c.sourceDate,
      refDate: REF,
      ...props,
    },
  })

describe('MvmMobileCatalog.vue — 6 檔 chips + section title + full list, no buy/online toggle', () => {
  it('renders all 7 檔期 chips on the horizontal axis (Kimi 11-22: 黑色購物週 added)', () => {
    const w = mountAt()
    expect(w.findAll('.mvm-chip')).toHaveLength(7)
  })

  it('opens the first 檔期 with products and renders its FULL item list', () => {
    const w = mountAt()
    const w1 = c.tabs[1] // 66 products (tab[1] = 優惠期間 w1 after 黑色購物週 was inserted at [2])
    expect(w.findAll('.mvm-list')[0].attributes('data-active-tab')).toBe('fy27p3-mvm2-w1')
    expect(w.findAll('.m-card')).toHaveLength(w1.products.length)
  })

  it('renders the section title in the spec form N筆 · 檔期名 · MM/DD ~ MM/DD · 剩 K 天', () => {
    const w = mountAt()
    const h = sectionHeader(c.tabs[1], REF)
    const title = w.findAll('[data-mvm-section-title]')[0].text()
    expect(title).toContain(h.count)
    expect(title).toContain('10/26 ~ 11/22') // Kimi 11-22: full range, no "到 " prefix
    expect(title).toContain('剩 2 天')
    expect(title).toBe(h.text) // the whole string, in the spec order
  })

  it('has a round white 篩選 button and NO 買場/線上 toggle (this is the 檔期 view)', () => {
    const w = mountAt()
    expect(w.find('[data-mvm-filter]').exists()).toBe(true)
    // the segmented 買場/線上 control from the HOME mockup must NOT be here
    expect(w.find('[data-buyonline-toggle]').exists()).toBe(false)
    expect(w.find('.mvm-seg').exists()).toBe(false)
  })

  it('the 篩選 button flips aria-pressed on click', async () => {
    const w = mountAt()
    const f = w.find('[data-mvm-filter]')
    expect(f.attributes('aria-pressed')).toBe('false')
    await f.trigger('click')
    expect(f.attributes('aria-pressed')).toBe('true')
  })

  it('clicking a chip swaps the active 檔期 grid to its full list', async () => {
    const w = mountAt()
    // Click 線上專屬 chip via its tab-id (index shifted after 黑色購物週 was inserted at [2])
    const cyberChip = w.find('[data-tab-id="fy27p4-mvm2-cyber"]')
    expect(cyberChip.exists()).toBe(true)
    await cyberChip.trigger('click')
    expect(w.findAll('.mvm-list')[0].attributes('data-active-tab')).toBe('fy27p4-mvm2-cyber')
    expect(w.findAll('.m-card')).toHaveLength(c.tabs[3].products.length) // index 3 after insert
  })

  it('an empty 檔期 shows the empty-state, not a blank list', async () => {
    const w = mountAt({ initialTab: 'fy27p4-mvm2-cyberland' })
    expect(w.find('.mvm-empty').exists()).toBe(true)
    expect(w.findAll('.m-card')).toHaveLength(0)
  })

  it('passes the 檔期 range "MM/DD ~ MM/DD" through to each card as a date chip (no "到 " prefix)', () => {
    const w = mountAt()
    // the active 檔期 (w1) 10/26 ~ 11/22; every card shows "10/26 ~ 11/22" (Kimi 11-22 format)
    const dateChips = w.findAll('.m-badge-date')
    expect(dateChips.length).toBeGreaterThan(0)
    expect(dateChips[0].text()).toBe('10/26 ~ 11/22')
    expect(w.text()).toContain('10/26 ~ 11/22')
  })
})

describe('MvmMobileCatalog.vue — 已過期 檔期 移除 + chip slider (#49 Kimi corrections)', () => {
  it('renders ONLY the active 檔期 chips; the 已過期 one (到 11/20) is absent from the DOM', () => {
    const w = mountAt({ refDate: new Date(2026, 10, 21) }) // pin today to 11/21
    const chips = w.findAll('.mvm-chip')
    expect(chips).toHaveLength(6) // 7 檔期 − 1 已過期 (到 11/20) = 6
    expect(w.find('[data-tab-id="fy27p3-mvm2-weekday"]').exists()).toBe(false) // 到 11/20 -> gone
    expect(w.find('[data-tab-id="fy27p3-mvm2-w1"]').exists()).toBe(true) // 到 11/22 -> kept
    expect(w.find('[data-tab-id="fy27p4-mvm2-cyberland"]').exists()).toBe(true) // 網購星期一 敬請期待 -> kept
    expect(w.find('[data-tab-id="fy27p4-mvm2-blackfriday"]').exists()).toBe(true) // 黑色購物週 敬請期待 -> kept
  })

  it('each dated 檔期 chip stacks the name over its range (two lines); no-date reads 敬請期待', () => {
    const w = mountAt() // REF 11/20 -> all 7 active
    const w1 = w.find('[data-tab-id="fy27p3-mvm2-w1"]') // 10/26 ~ 11/22 (two lines)
    expect(w1.find('.mvm-chip-label').exists()).toBe(true)
    expect(w1.find('.mvm-chip-end').exists()).toBe(true)
    expect(w1.find('.mvm-chip-label').text()).toBe('優惠期間')
    expect(w1.find('.mvm-chip-end').text()).toBe('10/26 ~ 11/22') // Kimi 11-22: range format
    // the no-date 檔期 (黑色購物週 / 網購星期一) shows "敬請期待", not blank (Kimi 11-22)
    const blackFriday = w.find('[data-tab-id="fy27p4-mvm2-blackfriday"]')
    expect(blackFriday.find('.mvm-chip-label').text()).toBe('黑色購物週')
    expect(blackFriday.find('.mvm-chip-end').exists()).toBe(true)
    expect(blackFriday.find('.mvm-chip-end').text()).toBe('敬請期待')
    const cyberland = w.find('[data-tab-id="fy27p4-mvm2-cyberland"]')
    expect(cyberland.find('.mvm-chip-label').text()).toBe('網購星期一')
    expect(cyberland.find('.mvm-chip-end').text()).toBe('敬請期待')
  })

  it('the default active skips an EXPIRED first 檔期 and opens the first OPEN one with products', () => {
    const tabs = [
      {
        tab_id: 'ex-first', label: '已結束', period: '2026/01/01 ~ 11/05',
        n_products: 5, products: [{ sku: 1 }, { sku: 2 }, { sku: 3 }, { sku: 4 }, { sku: 5 }],
      },
      {
        tab_id: 'open-next', label: '進行中', period: '2026/11/10 ~ 12/31',
        n_products: 3, products: [{ sku: 6 }, { sku: 7 }, { sku: 8 }],
      },
    ]
    const w = mount(MvmMobileCatalog, {
      props: { tabs, priceTypes: c.priceTypes, sourceDate: '', refDate: new Date(2026, 10, 21) },
    })
    expect(w.find('[data-tab-id="ex-first"]').exists()).toBe(false) // 到 11/05 -> 已過期, removed
    expect(w.find('[data-tab-id="open-next"]').exists()).toBe(true)
    expect(w.findAll('.mvm-list')[0].attributes('data-active-tab')).toBe('open-next')
    expect(w.findAll('.m-card')).toHaveLength(3)
  })

  it('when EVERY 檔期 is 已過期 the view shows a graceful empty state, not raw data', () => {
    const tabs = [
      { tab_id: 'a', label: 'A', period: '2026/01/01 ~ 11/05', n_products: 3, products: [{ sku: 1 }, { sku: 2 }, { sku: 3 }] },
      { tab_id: 'b', label: 'B', period: '2026/01/01 ~ 02/01', n_products: 2, products: [{ sku: 4 }, { sku: 5 }] },
    ]
    const w = mount(MvmMobileCatalog, {
      props: { tabs, priceTypes: c.priceTypes, sourceDate: '2026/11/16', refDate: new Date(2026, 10, 21) },
    })
    expect(w.find('.mvm-empty-all').exists()).toBe(true)
    expect(w.find('.mvm-empty-all').text()).toBe('全部檔期已結束')
    expect(w.find('[data-tab-id="a"]').exists()).toBe(false)
    expect(w.find('[data-tab-id="b"]').exists()).toBe(false)
    expect(w.find('[data-mvm-filter]').exists()).toBe(false) // no section when nothing is open
    expect(w.find('.mvm-chip').exists()).toBe(false)
  })
})

describe('isPeriodExpired / activePeriods (#49) — only expired dropped, null-safe', () => {
  const REF = new Date(2026, 10, 21) // pin today to 11/21

  it('a 檔期 whose 結束日 is strictly before today is expired', () => {
    expect(isPeriodExpired({ tab_id: 'a', period: '2026/11/01 ~ 11/20' }, REF)).toBe(true)
  })

  it('an 結束日 equal to today is NOT expired (still live that day)', () => {
    expect(isPeriodExpired({ tab_id: 'b', period: '2026/11/01 ~ 11/21' }, REF)).toBe(false)
  })

  it('future 結束日 (11/22, 12/06, 12/18) are kept', () => {
    expect(isPeriodExpired({ period: '2026/11/27 ~ 11/22' }, REF)).toBe(false) // 到 11/22
    expect(isPeriodExpired({ period: '2026/11/27 ~ 12/06' }, REF)).toBe(false) // 到 12/06
    expect(isPeriodExpired({ period: '2026/11/30 ~ 12/18' }, REF)).toBe(false) // 到 12/18
  })

  it('a no-date / 敬請期待 / blank 檔期 is NEVER expired', () => {
    expect(isPeriodExpired({ tab_id: 'c', label: '網購星期一', period: '敬請期待' }, REF)).toBe(false)
    expect(isPeriodExpired({ tab_id: 'd', period: '' }, REF)).toBe(false)
    expect(isPeriodExpired({ tab_id: 'e', period: 'TBA' }, REF)).toBe(false)
  })

  it('is null-safe with no refDate (live clock) and on a null / empty tab', () => {
    expect(typeof isPeriodExpired({ period: '2026/01/01 ~ 11/20' })).toBe('boolean')
    expect(isPeriodExpired(null, REF)).toBe(false)
    expect(isPeriodExpired({}, REF)).toBe(false)
  })

  it('activePeriods drops the only 已過期 檔期 at 11/21 and keeps the rest incl. the no-date ones', () => {
    const out = activePeriods(c.tabs, REF)
    expect(out.map((t) => t.tab_id)).toEqual([
      'fy27p3-mvm2-w1', // 到 11/22
      'fy27p4-mvm2-blackfriday', // 黑色購物週 敬請期待 — no date, kept
      'fy27p4-mvm2-cyber', // 到 12/06
      'fy27p4-mvm2-weekday', // 到 12/18
      'fy27p4-mvm2-cyberland', // 敬請期待 (no date, kept)
      'fy27p4-mvm2-w2', // 到 12/20
    ])
    expect(out.find((t) => t.tab_id === 'fy27p3-mvm2-weekday')).toBeFalsy() // 到 11/20 -> 已過期
  })

  it('does NOT drop an empty-but-future 檔期 (Kimi only asked about expired)', () => {
    const out = activePeriods(c.tabs, REF)
    const w2 = out.find((t) => t.tab_id === 'fy27p4-mvm2-w2') // 到 12/20, 0 listed products
    expect(w2).toBeTruthy()
  })
})

describe('MvmMobileProductCard.vue — 約X折 badge + 買場/線上 last line (warm)', () => {
  const mountCard = (product, tabPriceType = '') =>
    mount(MvmMobileProductCard, {
      props: { product, tabPriceType, priceTypes: c.priceTypes, endDate: '11/22' },
    })

  it('renders 約 X 折 from zheOf and the 買場 $X · 線上 $Y last line', () => {
    const w = mountCard({
      sku: 154795,
      name: '五月花 厚棒抽取式衛生紙 100抽X60入',
      cat: '家清',
      type: 'online_only',
      orig: 1149,
      promo: 919,
      discount: 230,
    })
    expect(w.text()).toContain('約 8 折') // zheOf(1149->919) = 8
    expect(w.text()).toContain('買場 $1,149 · 線上 $919')
    expect(w.find('.m-card-promo').text()).toBe('$919')
    expect(w.find('.m-card-orig').text()).toBe('$1,149')
  })

  it('a store-only item reads 買場 $X · 買場 $Y', () => {
    const w = mountCard({ sku: 4, name: 'X', cat: '家電', orig: 449, promo: 359, type: 'store_only' }, 'store_only')
    expect(w.text()).toContain('買場 $449 · 買場 $359')
    expect(w.text()).not.toContain('線上')
  })

  it('a 1 折 and a 9 折 product show 約 1 折 / 約 9 折 (the 個位)', () => {
    expect(
      mountCard({ sku: 1, name: '金冠 速溶咖啡', orig: 1000, promo: 121, discount: 879, type: 'online_only' }).text(),
    ).toContain('約 1 折')
    expect(
      mountCard({ sku: 2, name: '王品 火鍋料', orig: 349, promo: 329, discount: 20, type: 'online_only' }).text(),
    ).toContain('約 9 折')
  })

  it('the heart toggle flips aria-pressed (視覺 only this pass)', async () => {
    const w = mountCard({ sku: 1, name: 'X', orig: 449, promo: 359, type: 'online_only' })
    const heart = w.find('.m-heart')
    expect(heart.attributes('aria-pressed')).toBe('false')
    await heart.trigger('click')
    expect(heart.attributes('aria-pressed')).toBe('true')
  })

  it('a missing figure reads N/A and never an em/en dash', () => {
    const w = mountCard({ sku: 3, name: '品項', orig: 1000, promo: null, type: 'online_only', discount: null })
    expect(w.text()).toContain('N/A')
    expect(w.text()).toContain('買場 $1,000 · 線上 N/A')
    expect(w.text()).not.toContain('—')
    expect(w.text()).not.toContain('–')
  })
})
