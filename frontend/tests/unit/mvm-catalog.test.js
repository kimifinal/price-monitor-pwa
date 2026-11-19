import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MvmCatalog from '../../src/components/MvmCatalog.vue'
import MvmProductCard from '../../src/components/MvmProductCard.vue'
import {
  loadMvmCatalog,
  filterByCategory,
  categoriesOf,
} from '../../src/lib/mvm.js'

// MVM 檔期目錄 (B4) — the catalog renders the baked 6-檔期 snapshot offline.
// These assert the behaviours the spec + mockup demand: 6 tab buttons, a lazy
// grid that switches on tab click, per-card orig/promo/折幅/badge, and N/A (never
// an em-dash) for a missing tab count or a null price figure.
describe('MvmCatalog.vue — 6 檔期 tab bar + lazy grid', () => {
  const c = loadMvmCatalog()
  const mountAt = (props = {}) =>
    mount(MvmCatalog, {
      props: {
        tabs: c.tabs,
        priceTypes: c.priceTypes,
        sourceDate: c.sourceDate,
        ...props,
      },
    })

  it('renders all 6 檔期 tabs + a 3-row type legend', () => {
    const w = mountAt()
    expect(w.findAll('.mvm-tab')).toHaveLength(6)
    expect(w.findAll('.mvm-legend-row')).toHaveLength(3)
  })

  it('opens the first tab that carries products by default (lazy: no empty grid)', () => {
    const w = mountAt()
    // first tab is an empty 檔期; the catalog auto-picks the first with products
    expect(w.find('.mvm-grid').attributes('data-active-tab')).toBe('fy27p3-mvm2-w1')
    expect(w.findAll('.mvm-card').length).toBeGreaterThan(0)
  })

  it('only the active 檔期 renders cards (lazy grid, Q2); clicking a tab swaps it', async () => {
    const w = mountAt()
    const w1Cards = w.findAll('.mvm-card').length
    expect(w1Cards).toBe(c.tabs[1].products.length) // 62, the w1 檔期

    // switch to the cyber 檔期 (index 2, 17 products) — w1 unmounts, cyber mounts
    await w.findAll('.mvm-tab')[2].trigger('click')
    expect(w.find('.mvm-grid').attributes('data-active-tab')).toBe('fy27p4-mvm2-cyber')
    expect(w.findAll('.mvm-card').length).toBe(c.tabs[2].products.length)

    // an empty 檔期 (cyberland, index 4) shows an empty-state, not a blank grid
    await w.findAll('.mvm-tab')[4].trigger('click')
    expect(w.find('.mvm-grid').attributes('data-active-tab')).toBe('fy27p4-mvm2-cyberland')
    expect(w.find('.mvm-empty').exists()).toBe(true)
    expect(w.findAll('.mvm-card')).toHaveLength(0)
  })

  it('shows N/A (never "—") for a 檔期 whose count is a note or 0', () => {
    const w = mountAt()
    const counts = w.findAll('.tab-count').map((n) => n.text())
    expect(counts.some((s) => s.includes('N/A'))).toBe(true)
    // gate 19: no em/en dash anywhere in the rendered copy
    expect(w.text()).not.toContain('—')
    expect(w.text()).not.toContain('–')
  })

  it('renders a footer carrying the crawl date', () => {
    const w = mountAt()
    expect(w.find('.mvm-foot').text()).toContain(c.sourceDate)
  })

  it('sorts + filters the active 檔期 via the chips (Q3/Q4)', async () => {
    const w = mountAt()
    // 3 sort chips (折幅/類別/金額)
    const sortChips = w.findAll('.mvm-chip')
    expect(sortChips.length).toBeGreaterThanOrEqual(3)
    // default sort = 折幅 desc, deepest discount first on w1
    // click a non-"全部" category chip and confirm the grid shrinks to that cat
    const cats = categoriesOf(c.tabs[1].products) // active tab is w1
    const firstCat = cats[0]
    const expected = filterByCategory(c.tabs[1].products, firstCat).length
    const chips = w.findAll('.mvm-chips')[1].findAll('button') // 2nd group = category filter
    await chips[1].trigger('click') // index 1 = first real category ("all" is index 0)
    expect(w.findAll('.mvm-card').length).toBe(expected)
    expect(expected).toBeGreaterThan(0)
  })

  // the default-tab prop is honoured
  it('honours the initialTab prop when it names a real 檔期', () => {
    const w = mountAt({ initialTab: 'fy27p4-mvm2-cyber' })
    expect(w.find('.mvm-grid').attributes('data-active-tab')).toBe('fy27p4-mvm2-cyber')
  })

  it('an explicit empty 檔期 is honoured (empty-state); an unknown tab falls back', () => {
    // a valid-but-empty tab named by the user still opens (it just shows the
    // empty-state); a made-up id falls back to the first 檔期 with products.
    const empty = mountAt({ initialTab: 'fy27p3-mvm2-weekday' })
    expect(empty.find('.mvm-grid').attributes('data-active-tab')).toBe('fy27p3-mvm2-weekday')
    expect(empty.find('.mvm-empty').exists()).toBe(true)
    expect(mountAt({ initialTab: 'no-such-tab' }).find('.mvm-grid').attributes('data-active-tab')).toBe(
      'fy27p3-mvm2-w1',
    )
  })

  it('toggles the sort chips (折幅/類別/金額) and pins aria-pressed', async () => {
    const w = mountAt()
    const sortChips = w.findAll('.mvm-chips')[0].findAll('button')
    const total = w.findAll('.mvm-card').length
    // 金額 (price) -> highest promo first; sorting never changes the count
    await sortChips[2].trigger('click')
    expect(sortChips[2].attributes('aria-pressed')).toBe('true')
    expect(w.findAll('.mvm-card').length).toBe(total)
    // 類別 (category) -> grouped; still the same set of cards
    await sortChips[1].trigger('click')
    expect(sortChips[1].attributes('aria-pressed')).toBe('true')
    expect(w.findAll('.mvm-card').length).toBe(total)
  })

  it('the 全部 category chip shows every product of the active 檔期', async () => {
    const w = mountAt()
    const catChips = w.findAll('.mvm-chips')[1].findAll('button') // 2nd group = category filter
    const total = c.tabs[1].products.length
    await catChips[0].trigger('click') // "全部"
    expect(catChips[0].attributes('aria-pressed')).toBe('true')
    expect(w.findAll('.mvm-card').length).toBe(total)
  })
})

describe('MvmProductCard.vue — orig/promo/折幅/badge + N/A on nulls', () => {
  const priceTypes = {
    online_only: { label: '僅限好市多線上購物', meaning: 'only online' },
    store_online_diff: { label: '賣場售價 / 線上亦有優惠', meaning: 'diff' },
    store_only: { label: '賣場獨家 / 平日限定', meaning: 'store only' },
  }
  const mountCard = (product) =>
    mount(MvmProductCard, { props: { product, priceTypes } })

  it('renders a normal card: orig line-through, promo, 省, 折幅 %, type badge (TWD, no .00)', () => {
    const w = mountCard({
      sku: 153085,
      name: 'CONAIR 美康雅 熨斗',
      cat: '家電',
      type: 'online_only',
      orig: 1999,
      promo: 1379,
      discount: 620,
    })
    expect(w.text()).toContain('TWD 1,999') // orig
    expect(w.text()).toContain('TWD 1,379') // promo
    expect(w.text()).toContain('省 TWD 620') // savings
    expect(w.text()).toContain('-31.0%') // 620/1999 = 31.0%, deep discount
    expect(w.find('.disc-high').exists()).toBe(true) // >=25% -> high tier
    expect(w.text()).toContain('僅限好市多線上購物') // badge label
    expect(w.find('.badge-online_only').exists()).toBe(true)
    // a pure-verb link, no glued arrow (gate 63)
    expect(w.find('.mvm-link').text()).toBe('查看')
  })

  it('shows N/A for a null orig/discount card (秤賣/特例品項), not "—"', () => {
    const w = mountCard({
      sku: 167247,
      name: '泰安 冷凍豬梅花火鍋片 秤賣',
      cat: '肉品',
      type: 'store_only_weight', // sub-variant -> falls back to store_only badge
      orig: null,
      promo: 86,
      discount: null,
      note: '$86/kg 秤賣',
    })
    expect(w.find('.mvm-orig').text()).toBe('N/A')
    expect(w.find('.mvm-discount').text()).toBe('N/A')
    expect(w.find('.mvm-save').text()).toBe('N/A')
    // sub-variant resolves to the store_only badge so it never renders empty
    expect(w.find('.badge-store_only').exists()).toBe(true)
    expect(w.find('.disc-low').exists()).toBe(true) // no computable discount -> low/muted
    // the note explains the N/A and renders
    expect(w.text()).toContain('$86/kg 秤賣')
    expect(w.text()).not.toContain('—')
  })

  it('a deep discount is high-tier; a shallow one is mid/low', () => {
    expect(mountCard({ orig: 100, discount: 30, type: 'online_only' }).find('.disc-high').exists()).toBe(true)
    expect(mountCard({ orig: 100, discount: 18, type: 'online_only' }).find('.disc-mid').exists()).toBe(true)
    expect(mountCard({ orig: 100, discount: 8, type: 'online_only' }).find('.disc-low').exists()).toBe(true)
  })

  it('renders the real product url when present, and omits the note when absent', () => {
    // a card WITH a url carries it on the "查看" link (MVM JSON usually has none).
    const withUrl = mountCard({ sku: 1, name: 'X', type: 'online_only', orig: 10, promo: 9, discount: 1, url: 'https://www.costco.com.tw/p/1' })
    expect(withUrl.find('.mvm-link').attributes('href')).toBe('https://www.costco.com.tw/p/1')
    // no `note` -> the note slot is not rendered
    expect(withUrl.find('.mvm-note').exists()).toBe(false)
    // a card with a null promo also shows N/A on the price slot
    const noPromo = mountCard({ sku: 9, name: 'Y', type: 'store_only', orig: null, promo: null, discount: null })
    expect(noPromo.find('.mvm-promo').text()).toBe('N/A')
  })
})

describe('MvmCatalog.vue — empty / edge paths', () => {
  // a catalog with a price_type lacking a meaning omits the meaning line
  it('omits a legend meaning when the price_type has none', () => {
    const w = mount(MvmCatalog, {
      props: {
        tabs: [],
        priceTypes: { online_only: { label: '線上' } }, // no `meaning`
        sourceDate: '',
      },
    })
    expect(w.find('.mvm-legend-meaning').exists()).toBe(false)
  })

  // with no source date the footer drops the "資料於 … 抓取" clause
  it('omits the crawl date in the footer when sourceDate is empty', () => {
    const w = mount(MvmCatalog, {
      props: { tabs: [], priceTypes: {}, sourceDate: '' },
    })
    expect(w.find('.mvm-foot').text()).not.toContain('資料於')
  })

  // an empty catalog renders the empty-state, not a blank grid
  it('shows the empty-state for a catalog with no products', () => {
    const w = mount(MvmCatalog, {
      props: {
        tabs: [{ tab_id: 'empty', label: '空', period: 'N/A', n_products: 0, products: [] }],
        priceTypes: {},
      },
    })
    expect(w.find('.mvm-empty').exists()).toBe(true)
    expect(w.findAll('.mvm-card')).toHaveLength(0)
  })
})
