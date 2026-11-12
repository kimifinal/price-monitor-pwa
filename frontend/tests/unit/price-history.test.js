import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PriceHistory from '../../src/components/PriceHistory.vue'

describe('PriceHistory.vue', () => {
  it('renders the name, current price and a verdict badge from the SSOT', () => {
    const card = {
      name: 'BOSE Solo Soundbar',
      current: 8149,
      series: [10000, 9500, 9200, 8600, 8149],
      metrics: { points: 5, atAllTimeLow: true, dropPctFromHigh: 18.5 },
      url: 'https://example.com/sku',
    }
    const w = mount(PriceHistory, { props: { card } })
    expect(w.text()).toContain('BOSE Solo Soundbar')
    expect(w.text()).toContain('8,149')
    expect(w.text()).toContain('歷史最低') // verdict from monitor.js, not the component
    expect(w.find('path').exists()).toBe(true) // a sparkline is drawn
    expect(w.get('a').attributes('href')).toBe('https://example.com/sku')
  })

  it('shows 尚無歷史 for a card without a series', () => {
    const card = { name: 'Mystery', current: 0, series: [], metrics: { points: 0 } }
    const w = mount(PriceHistory, { props: { card } })
    expect(w.text()).toContain('尚無歷史')
    expect(w.find('path').exists()).toBe(false)
  })

  it('sets data-verdict so a good-deal card is visually distinguishable', () => {
    const card = {
      name: 'A',
      current: 100,
      series: [200, 150, 100],
      metrics: { points: 3, atAllTimeLow: false, dropPctFromHigh: 50 },
    }
    const w = mount(PriceHistory, { props: { card } })
    expect(w.find('.price-history').attributes('data-verdict')).toBe('good_deal')
  })

  it('defaults a retailer card to the costco source badge', () => {
    const card = {
      name: 'BOSE Solo Soundbar',
      current: 8149,
      series: [10000, 9500, 8149],
      metrics: { points: 3, atAllTimeLow: true, dropPctFromHigh: 18.5 },
    }
    const w = mount(PriceHistory, { props: { card } })
    expect(w.get('.price-history').attributes('data-source')).toBe('costco')
    expect(w.text()).toContain('🛒')
  })
})
