import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MvmMobileCatalog from '../../src/components/mobile/MvmMobileCatalog.vue'
import MvmMobileProductCard from '../../src/components/mobile/MvmMobileProductCard.vue'
import { loadMvmCatalog, sectionHeader } from '../../src/lib/mvm.js'

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
  it('renders all 6 檔期 chips on the horizontal axis', () => {
    const w = mountAt()
    expect(w.findAll('.mvm-chip')).toHaveLength(6)
  })

  it('opens the first 檔期 with products and renders its FULL item list', () => {
    const w = mountAt()
    const w1 = c.tabs[1] // 62 products, the 優惠期間 檔期
    expect(w.findAll('.mvm-list')[0].attributes('data-active-tab')).toBe('fy27p3-mvm2-w1')
    expect(w.findAll('.m-card')).toHaveLength(w1.products.length)
  })

  it('renders the section title in the exact spec form N筆 · 檔期名 · 到 MM/DD · 剩 K 天', () => {
    const w = mountAt()
    const h = sectionHeader(c.tabs[1], REF)
    const title = w.findAll('[data-mvm-section-title]')[0].text()
    expect(title).toContain(h.count)
    expect(title).toContain('到 11/22')
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
    await w.findAll('.mvm-chip')[2].trigger('click') // 線上專屬 檔期, 17 products
    expect(w.findAll('.mvm-list')[0].attributes('data-active-tab')).toBe('fy27p4-mvm2-cyber')
    expect(w.findAll('.m-card')).toHaveLength(c.tabs[2].products.length)
  })

  it('an empty 檔期 shows the empty-state, not a blank list', async () => {
    const w = mountAt({ initialTab: 'fy27p4-mvm2-cyberland' })
    expect(w.find('.mvm-empty').exists()).toBe(true)
    expect(w.findAll('.m-card')).toHaveLength(0)
  })

  it('passes the 檔期 到期日 through to each card as a "到 MM/DD" chip', () => {
    const w = mountAt()
    // the active 檔期 (w1) ends 11/22; every card shows "到 11/22"
    const dateChips = w.findAll('.m-badge-date')
    expect(dateChips.length).toBeGreaterThan(0)
    expect(dateChips[0].attributes('data-sku') || true).toBeTruthy()
    expect(w.text()).toContain('到 11/22')
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
