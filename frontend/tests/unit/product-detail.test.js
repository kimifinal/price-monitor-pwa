import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ProductDetail from '../../src/components/mobile/ProductDetail.vue'
import MobileApp from '../../src/components/mobile/MobileApp.vue'
import MvmMobileCatalog from '../../src/components/mobile/MvmMobileCatalog.vue'
import CatalogMobile from '../../src/components/mobile/CatalogMobile.vue'
import {
  priceOf,
  isOnlineOnly,
  isAvailable,
  saveOf,
  zheOfItem,
  saveTextOf,
  endDateChip,
  promoRecord,
  costcoUrl,
  buildDetailModel,
  money,
} from '../../src/lib/detail.js'

// #53 — 商品詳情頁 (Product Detail) unit tests.
// Tests cover pure model helpers (lib/detail.js), ProductDetail.vue rendering,
// CTA events, card navigation in MobileApp, back navigation, and offline rendering.

const DUMMY_CATALOG_ITEM = {
  sku: '153289',
  name: '伊萊克斯 無線吸塵器 WQ71-2BSWF',
  price: 5199,
  basePrice: 6899,
  discount: 1700,
  online_only: false,
  stock: 'inStock',
}

const DUMMY_ONLINE_ITEM = {
  sku: '129240',
  name: '永備 碳鋅 1號電池 24入',
  price: 499,
  basePrice: 499,
  discount: 0,
  online_only: true,
  stock: 'inStock',
}

const DUMMY_MVM_ITEM = {
  sku: 154795,
  name: '五月花 厚棒抽取式衛生紙 100抽X60入',
  orig: 1149,
  promo: 919,
  discount: 230,
  type: 'online_only',
  cat: '家清',
}

describe('lib/detail.js — pure model helpers', () => {
  it('priceOf normalizes catalog (price/basePrice) and MVM (promo/orig)', () => {
    expect(priceOf(DUMMY_CATALOG_ITEM)).toEqual({ now: 5199, orig: 6899 })
    expect(priceOf(DUMMY_MVM_ITEM)).toEqual({ now: 919, orig: 1149 })
    expect(priceOf(null)).toEqual({ now: null, orig: null })
  })

  it('isOnlineOnly recognizes both online_only bool and type string', () => {
    expect(isOnlineOnly(DUMMY_ONLINE_ITEM)).toBe(true)
    expect(isOnlineOnly(DUMMY_MVM_ITEM)).toBe(true)
    expect(isOnlineOnly(DUMMY_CATALOG_ITEM)).toBe(false)
  })

  it('isAvailable checks stock string with null safety', () => {
    expect(isAvailable(DUMMY_CATALOG_ITEM)).toBe(true)
    expect(isAvailable({ stock: 'outOfStock' })).toBe(false)
    expect(isAvailable({})).toBe(true)
  })

  it('saveOf and saveTextOf calculate savings correctly', () => {
    expect(saveOf(DUMMY_CATALOG_ITEM)).toBe(1700)
    expect(saveTextOf(DUMMY_CATALOG_ITEM)).toBe('省 $1,700')
    expect(saveOf({ price: 100, basePrice: 100 })).toBeNull()
    expect(saveTextOf({ price: 100, basePrice: 100 })).toBe('')
  })

  it('zheOfItem calculates the 個位 折', () => {
    expect(zheOfItem(DUMMY_CATALOG_ITEM)).toBe(8) // 5199/6899 = 0.753 -> 8 折
    expect(zheOfItem({ price: 100, basePrice: 100 })).toBeNull()
  })

  it('endDateChip formats date ranges and hides empty/N/A', () => {
    expect(endDateChip('10/26 ~ 11/22')).toBe('10/26 ~ 11/22')
    expect(endDateChip('11/22')).toBe('到 11/22')
    expect(endDateChip('敬請期待')).toBe('')
    expect(endDateChip('')).toBe('')
  })

  // #55 特價紀錄 (promoRecord): the 賣場 row is driven by a REAL costco-history
  // series; the 線上 row has no series yet (#56) and shows an honest placeholder,
  // never a faked curve.
  describe('promoRecord (#55)', () => {
    // a realistic costco-history record with a real downward price series:
    // 720 → 680 → 680 → 549 → 480 → 549 = three strictly-downward steps.
    const HISTORY_RECORD = {
      sku: '100001',
      name: 'Kirkland 綜合維他命 C 1000mg',
      current: 549,
      low: 480,
      high: 720,
      drop_pct_from_high: 24,
      at_all_time_low: false,
      points: 6,
      series: [
        { observed_at: '2026-09-01', price: 720, source: 'costco' },
        { observed_at: '2026-09-15', price: 680, source: 'costco' },
        { observed_at: '2026-10-01', price: 680, source: 'costco' },
        { observed_at: '2026-10-15', price: 549, source: 'costco' },
        { observed_at: '2026-10-20', price: 480, source: 'costco' },
        { observed_at: '2026-11-01', price: 549, source: 'costco' },
      ],
    }

    it('is null-safe: a null record yields a well-formed 尚無歷史 model (no throw)', () => {
      const r = promoRecord({ sku: '1', name: 'X', price: 100, basePrice: 100 }, null)
      expect(r.hasHistory).toBe(false)
      expect(r.store.hasHistory).toBe(false)
      expect(r.store.series).toEqual([])
      expect(r.store.spark).toBe('')
      // gate 19: no undefined / '-' / .00 — nulls read as 'N/A', 省 is hidden
      expect(r.store.now).toBeNull()
      expect(r.store.nowText).toBe('N/A')
      expect(r.store.low).toBeNull()
      expect(r.store.lowText).toBe('N/A')
      expect(r.store.save).toBeNull()
      expect(r.store.saveText).toBe('')
      expect(r.store.drops).toBe(0)
      expect(r.store.verdict.key).toBe('unknown')
      // the 線上 row still shows the current online price + an honest placeholder
      expect(r.online.hasSeries).toBe(false)
      expect(r.online.now).toBe(100)
      expect(r.online.note).toMatch(/待補/)
    })

    it('a missing record (undefined) is treated the same as null (gate 19)', () => {
      expect(promoRecord({ sku: '1', price: 100 }, undefined).hasHistory).toBe(false)
    })

    it('never throws on a null item + null record', () => {
      expect(() => promoRecord(null, null)).not.toThrow()
      const r = promoRecord(null, null)
      expect(r.hasHistory).toBe(false)
      expect(r.store.verdict.key).toBe('unknown')
    })

    it('a malformed record (no series / low / current) yields 尚無歷史, not a throw', () => {
      const r = promoRecord({ sku: '1', price: 100 }, { sku: '1' })
      expect(r.hasHistory).toBe(false)
      expect(r.store.now).toBeNull()
      expect(r.store.spark).toBe('')
    })

    it('a real history record renders drops / 一年最低 / 現價 / 省 / verdict', () => {
      const item = { sku: '100001', name: 'Kirkland', price: 549, basePrice: 699 }
      const r = promoRecord(item, HISTORY_RECORD, '10/20 ~ 10/26')
      expect(r.hasHistory).toBe(true)
      expect(r.store.hasHistory).toBe(true)
      // 特價幾次 = three strictly-downward steps
      expect(r.store.drops).toBe(3)
      // 現價 / 一年最低 read from the record (the 賣場 row uses the record)
      expect(r.store.now).toBe(549)
      expect(r.store.nowText).toBe('$549')
      expect(r.store.low).toBe(480)
      expect(r.store.lowText).toBe('$480')
      // 省 = 原價 − 現價 (699 − 549 = 150)
      expect(r.store.save).toBe(150)
      expect(r.store.saveText).toMatch(/150/)
      // 檔期 passthrough (a '~' range is not '到'-prefixed)
      expect(r.store.end).toBe('10/20 ~ 10/26')
      // a real sparkline path (a polyline, never a faked/empty curve)
      expect(r.store.spark).toMatch(/^M/)
      expect(r.store.spark.split('L').length).toBeGreaterThan(3)
      // verdict is a valid key with a clean (emoji-free) label
      expect(['all_time_low', 'good_deal', 'near_high', 'stable', 'unknown']).toContain(
        r.store.verdict.key,
      )
      expect(r.store.verdict.label.trim().length).toBeGreaterThan(0)
      expect(/[一-龥]/u.test(r.store.verdict.label)).toBe(true)
      // the 線上 row: current online price + placeholder, never a faked series
      expect(r.online.now).toBe(549)
      expect(r.online.money).toBe('$549')
      expect(r.online.hasSeries).toBe(false)
      expect(r.online.note).toMatch(/待補/)
    })
  })

  it('costcoUrl forms a valid search link', () => {
    const url = costcoUrl(DUMMY_CATALOG_ITEM)
    expect(url).toContain('https://www.costco.com.tw/search/?q=')
    expect(url).toContain(encodeURIComponent(DUMMY_CATALOG_ITEM.name))
  })

  it('buildDetailModel returns full structured detail model', () => {
    const m = buildDetailModel(DUMMY_CATALOG_ITEM, { endDate: '10/26 ~ 11/22' })
    expect(m.sku).toBe('153289')
    expect(m.name).toBe(DUMMY_CATALOG_ITEM.name)
    expect(m.store.now).toBe(5199)
    expect(m.store.orig).toBe(6899)
    expect(m.online.now).toBe(5199)
    expect(m.save).toBe(1700)
    expect(m.zhe).toBe(8)
    expect(m.endDate).toBe('10/26 ~ 11/22')
    // #55 特價紀錄: a promo model (online placeholder when no history record).
    expect(m.promo).toBeTruthy()
    expect(m.promo.online.note).toMatch(/待補/)
  })

  it('money formats TWD with $ prefix and handles nulls gracefully', () => {
    expect(money(5199)).toBe('$5,199')
    expect(money(null)).toBe('N/A')
  })
})

describe('ProductDetail.vue — component rendering & interactions', () => {
  it('renders top appbar with title, back button, share, and track buttons', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    expect(w.find('.detail-back').text()).toContain('完成')
    expect(w.find('.detail-title').text()).toContain('商品詳情')
    expect(w.find('[data-share]').exists()).toBe(true)
    expect(w.find('[data-track]').exists()).toBe(true)
  })

  it('renders product image placeholder, title, and SKU', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    expect(w.find('[data-detail-image]').exists()).toBe(true)
    expect(w.find('[data-detail-name]').text()).toBe(DUMMY_CATALOG_ITEM.name)
    expect(w.find('[data-detail-sku]').text()).toContain('153289')
  })

  it('renders store and online price sections with main prices and notes', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    expect(w.find('[data-section-store] [data-store-now]').text()).toBe('$5,199')
    expect(w.find('[data-section-online] [data-online-now]').text()).toBe('$5,199')
    expect(w.find('[data-section-store]').text()).toContain('會員護照價，以賣場為準')
  })

  it('#55 特價紀錄: 賣場 row shows 尚無歷史 when no history record (規格摘要 is gone)', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    // 規格摘要 (#53) is replaced by 特價紀錄 (#55)
    expect(w.find('[data-section-specs]').exists()).toBe(false)
    expect(w.find('.detail-specs').exists()).toBe(false)
    const promoSec = w.find('[data-section-promo]')
    expect(promoSec.exists()).toBe(true)
    expect(promoSec.text()).toContain('特價紀錄')
    // 賣場 row with no record → 尚無歷史 (never a faked curve / '-' / .00)
    expect(w.find('[data-promo-empty]').text()).toContain('尚無歷史')
    expect(w.find('[data-promo-spark]').exists()).toBe(false)
    // 線上 row shows the current online price + an honest placeholder
    expect(w.find('[data-promo-online-now]').exists()).toBe(true)
    expect(w.find('[data-promo-online-note]').text()).toMatch(/待補/)
  })

  it('#55 特價紀錄: 賣場 row renders the real series (sparkline + 特價幾次 / 一年最低 / 現價 / 省)', () => {
    const record = {
      sku: '100001',
      current: 549,
      low: 480,
      high: 720,
      drop_pct_from_high: 24,
      at_all_time_low: false,
      points: 6,
      series: [
        { observed_at: '2026-09-01', price: 720, source: 'costco' },
        { observed_at: '2026-09-15', price: 680, source: 'costco' },
        { observed_at: '2026-10-01', price: 680, source: 'costco' },
        { observed_at: '2026-10-15', price: 549, source: 'costco' },
        { observed_at: '2026-10-20', price: 480, source: 'costco' },
        { observed_at: '2026-11-01', price: 549, source: 'costco' },
      ],
    }
    const item = {
      sku: '100001',
      name: 'Kirkland 綜合維他命 C 1000mg',
      price: 549,
      basePrice: 699,
    }
    const w = mount(ProductDetail, {
      props: { product: item, endDate: '10/20 ~ 10/26', historyRecord: record },
    })
    const promoSec = w.find('[data-section-promo]')
    expect(promoSec.exists()).toBe(true)
    // a real sparkline path (a polyline, never a faked/empty curve)
    const spark = w.find('[data-promo-spark]')
    expect(spark.exists()).toBe(true)
    expect(spark.find('path').attributes('d')).toMatch(/^M/)
    // 特價幾次 = 3 downward steps; 一年最低 / 現價 from the record
    expect(w.find('[data-promo-drops]').text()).toContain('3')
    expect(w.find('[data-promo-low]').text()).toContain('480')
    expect(w.find('[data-promo-now]').text()).toContain('549')
    // 省 badge (原價 699 − 現價 549 = 150)
    expect(w.find('[data-promo-save]').text()).toContain('150')
    // verdict renders with a clean (emoji-free) label
    expect(w.find('.detail-promo-verdict').text().trim().length).toBeGreaterThan(0)
    // 線上 row: current online price + placeholder, never a faked series
    expect(w.find('[data-promo-online-now]').text()).toContain('549')
    expect(w.find('[data-promo-online-note]').text()).toMatch(/待補/)
  })

  it('renders bottom CTA bar with primary and secondary buttons', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    expect(w.find('[data-notify]').text()).toContain('下次特價通知我')
    const openWeb = w.find('[data-open-web]')
    expect(openWeb.text()).toContain('到官網看')
    expect(openWeb.attributes('href')).toContain('https://www.costco.com.tw')
  })

  it('emits back event when clicking back button', async () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    await w.find('.detail-back').trigger('click')
    expect(w.emitted('back')).toBeTruthy()
  })

  it('toggles tracking state and emits toggle-track event', async () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    const btn = w.find('[data-track]')
    expect(btn.classes()).not.toContain('is-active')
    await btn.trigger('click')
    expect(btn.classes()).toContain('is-active')
    expect(w.emitted('toggle-track')).toEqual([[true]])
  })

  it('toggles notify CTA state and emits notify event', async () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    const btn = w.find('[data-notify]')
    expect(btn.text()).toContain('下次特價通知我')
    await btn.trigger('click')
    expect(btn.text()).toContain('已設通知')
    expect(w.emitted('notify')).toEqual([[true]])
  })

  it('emits verify event when clicking 價格不對？', async () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    await w.find('[data-verify]').trigger('click')
    expect(w.emitted('verify')).toBeTruthy()
    expect(w.emitted('verify')[0][0]).toEqual(DUMMY_CATALOG_ITEM)
  })
})

describe('MobileApp.vue — card to detail navigation and back', () => {
  it('opens detail view when clicking a card in 特價 (MVM) view', async () => {
    const w = mount(MobileApp)
    // Default active is 'deal' (MVM catalog)
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
    expect(w.findComponent(ProductDetail).exists()).toBe(false)

    // Click the first card
    const card = w.find('.m-card')
    expect(card.exists()).toBe(true)
    await card.trigger('click')

    // Detail view is now visible
    expect(w.findComponent(ProductDetail).exists()).toBe(true)

    // Click back (完成)
    await w.find('.detail-back').trigger('click')

    // Returns to MVM catalog
    expect(w.findComponent(ProductDetail).exists()).toBe(false)
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
  })

  it('opens detail view when clicking a card in 全部 (Catalog) view', async () => {
    const w = mount(MobileApp)
    // Switch to 全部 tab
    await w.findAll('.m-tab')[3].trigger('click')
    expect(w.findComponent(CatalogMobile).exists()).toBe(true)

    // Click first card in catalog
    const card = w.find('.m-cat-card')
    expect(card.exists()).toBe(true)
    await card.trigger('click')

    // Detail view open
    expect(w.findComponent(ProductDetail).exists()).toBe(true)

    // Click back
    await w.find('.detail-back').trigger('click')

    // Returns to 全部 tab
    expect(w.findComponent(CatalogMobile).exists()).toBe(true)
  })

  it('clicking heart on a card toggles wish without opening detail view', async () => {
    const w = mount(MobileApp)
    const heart = w.find('.m-heart')
    expect(heart.exists()).toBe(true)

    await heart.trigger('click')

    // Still in MVM catalog, detail view is NOT opened
    expect(w.findComponent(ProductDetail).exists()).toBe(false)
    expect(w.findComponent(MvmMobileCatalog).exists()).toBe(true)
  })
})
