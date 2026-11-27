import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { onlineRecordBySku } from '../../src/lib/mvm.js'
import { promoRecord } from '../../src/lib/detail.js'
import ProductDetail from '../../src/components/mobile/ProductDetail.vue'
import mvmData from '../../src/data/mvm.json'

// #56 — 線上(online)歷史序列 接進商品詳情頁。
//
// The MVM 檔期 snapshot already carries each product's orig (原價) + promo (優惠價).
// #56 builds the online price series FROM THAT DATA (two points per 檔期: orig at
// the 檔期 start, promo at the 檔期 end) so the 線上 row can render a REAL curve —
// never a faked one. A sku with no MVM 檔期 keeps the honest "待補" placeholder.

// The 3 skus that overlap costco-history.json (the online curve has real data).
const MVM_OVERLAP = ['144129', '153555', '1646074']

// A sku that is NOT in any MVM 檔期 → no online series → placeholder.
const NON_MVM_SKU = '999999'

// Build the {orig, promo, period} for a sku from the source snapshot (SSOT), so the
// test cross-checks the builder against the data it must come from — not hardcoded.
function mvmProductFor(sku) {
  const hit = mvmData.tabs.flatMap((t) =>
    Array.isArray(t.products)
      ? t.products.filter((p) => String(p.sku) === String(sku)).map((p) => ({ tab: t, product: p }))
      : [],
  )
  return hit[0] || null
}

describe('#56 onlineRecordBySku (lib/mvm.js)', () => {
  it('builds a 2-point online series from the MVM orig + promo', () => {
    for (const sku of MVM_OVERLAP) {
      const rec = onlineRecordBySku(sku)
      expect(rec, `sku ${sku} should have an online record`).not.toBeNull()
      expect(rec.hasSeries).toBe(true)
      expect(rec.source).toBe('online')
      // orig + promo = 2 points, ordered by 檔期 start → end.
      expect(rec.series).toHaveLength(2)
      expect(rec.points).toBe(2)
      expect(rec.series[0].source).toBe('online')
      expect(rec.series[1].source).toBe('online')

      // The two points come straight from the MVM orig (start) + promo (end).
      const { product } = mvmProductFor(sku)
      expect(rec.series[0].price).toBe(Number(product.orig))
      expect(rec.series[1].price).toBe(Number(product.promo))

      // Metrics: current = latest (promo), low = min, high = max.
      expect(rec.current).toBe(Number(product.promo))
      expect(rec.low).toBe(Math.min(Number(product.orig), Number(product.promo)))
      expect(rec.high).toBe(Math.max(Number(product.orig), Number(product.promo)))

      // A real drop from the high → a positive drop_pct_from_high.
      expect(rec.drop_pct_from_high).toBeGreaterThan(0)
    }
  })

  it('parses the 檔期 "2026/10/26 ~ 11/22 優惠期間" into ISO start + end', () => {
    const rec = onlineRecordBySku('144129')
    // 2026/10/26 ~ 11/22 → 2026-10-26 .. 2026-11-22 (single-digit month stays 2-digit ISO).
    expect(rec.series[0].observed_at).toBe('2026-10-26')
    expect(rec.series[1].observed_at).toBe('2026-11-22')
  })

  it('returns null for a sku with no MVM 檔期 (placeholder path)', () => {
    expect(onlineRecordBySku(NON_MVM_SKU)).toBeNull()
    expect(onlineRecordBySku('does-not-exist')).toBeNull()
    expect(onlineRecordBySku(null)).toBeNull()
  })
})

describe('#56 promoRecord online row (lib/detail.js)', () => {
  it('renders a curve when the online record has a series', () => {
    for (const sku of MVM_OVERLAP) {
      const online = onlineRecordBySku(sku)
      // A catalog/MVM item; the online row reads ONLY from the online record.
      const r = promoRecord({ sku, name: 'X' }, null, '', online)
      expect(r.online.hasSeries, `sku ${sku}`).toBe(true)
      expect(Array.isArray(r.online.series)).toBe(true)
      expect(r.online.series.length).toBeGreaterThan(1)
      // sparkPath produces an "M…L…" path with > 1 point.
      expect(r.online.spark).toMatch(/^M/)
      expect(r.online.spark.split('L').length).toBeGreaterThan(1)
      // verdict + metrics mirrored from 賣場.
      expect(r.online.verdict).toHaveProperty('key')
      expect(typeof r.online.drops).toBe('number')
      expect(r.online.drops).toBeGreaterThanOrEqual(1)
      expect(r.online.lowText).toMatch(/^\$/)
      expect(r.online.nowText).toMatch(/^\$/)
    }
  })

  it('keeps the "待補" placeholder when there is no online record', () => {
    const r = promoRecord({ sku: NON_MVM_SKU, name: 'X' }, null, '', null)
    expect(r.online.hasSeries).toBe(false)
    expect(r.online.note).toMatch(/待補/)
    // No series / spark / verdict in the placeholder path.
    expect(r.online.series).toBeUndefined()
    expect(r.online.spark).toBeUndefined()
    expect(r.online.verdict).toBeUndefined()
  })

  it('defaults to the placeholder when no online record arg is passed', () => {
    // Mirrors the pre-#56 call shape (onlineRecord undefined) — must not crash.
    const r = promoRecord({ sku: '153289', name: 'X' })
    expect(r.online.hasSeries).toBe(false)
    expect(r.online.note).toMatch(/待補/)
  })
})

describe('#56 ProductDetail online row rendering', () => {
  it('renders the online sparkline for every MVM-overlap sku', async () => {
    // All three costco-overlap skus render a real curve through the UI — not just
    // one — so the 線上 row is proven for 144129 / 153555 / 1646074.
    for (const sku of MVM_OVERLAP) {
      const online = onlineRecordBySku(sku)
      const wrapper = mount(ProductDetail, {
        props: {
          product: { sku, name: '線上商品' },
          onlineRecord: online,
        },
      })
      // The online row renders a curve (spark path) — not just a placeholder note.
      expect(wrapper.find('[data-promo-online-spark]').exists(), `sku ${sku} spark`).toBe(true)
      expect(wrapper.find('[data-promo-online-spark] path').exists(), `sku ${sku} path`).toBe(true)
      expect(wrapper.find('[data-promo-online-drops]').exists(), `sku ${sku} drops`).toBe(true)
      // The placeholder note is gone when a real series renders.
      expect(wrapper.find('[data-promo-online-note]').exists(), `sku ${sku} note`).toBe(false)
      await wrapper.vm.$nextTick()
    }
  })

  it('keeps the placeholder note when no online record is passed', async () => {
    const wrapper = mount(ProductDetail, {
      props: {
        product: { sku: NON_MVM_SKU, name: '非 MVM 商品' },
      },
    })
    expect(wrapper.find('[data-promo-online-note]').exists()).toBe(true)
    expect(wrapper.text()).toContain('待補')
    expect(wrapper.find('[data-promo-online-spark]').exists()).toBe(false)
    await wrapper.vm.$nextTick()
  })
})
