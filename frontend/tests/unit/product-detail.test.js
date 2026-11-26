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
  specList,
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

  it('specList provides 4 placeholder fields reading 待補', () => {
    const list = specList(DUMMY_CATALOG_ITEM)
    expect(list).toHaveLength(4)
    expect(list.map((f) => f.label)).toEqual(['吸力', '重量', '使用時間', '濾網'])
    expect(list.every((f) => f.value === '待補')).toBe(true)
    expect(list.every((f) => f.placeholder)).toBe(true)
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
    expect(m.specs).toHaveLength(4)
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

  it('renders 規格摘要 2-column grid with 4 placeholder items', () => {
    const w = mount(ProductDetail, { props: { product: DUMMY_CATALOG_ITEM } })
    const specsSec = w.find('[data-section-specs]')
    expect(specsSec.exists()).toBe(true)
    expect(specsSec.text()).toContain('規格摘要')
    expect(specsSec.text()).toContain('吸力')
    expect(specsSec.text()).toContain('重量')
    expect(specsSec.text()).toContain('使用時間')
    expect(specsSec.text()).toContain('濾網')
    expect(specsSec.text()).toContain('規格欄待補')
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
