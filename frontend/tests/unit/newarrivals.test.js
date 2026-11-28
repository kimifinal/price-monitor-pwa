import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NewArrivalsMobile from '../../src/components/mobile/NewArrivalsMobile.vue'
import {
  newArrivals,
  categories as deriveCategories,
} from '../../src/lib/newarrivals.js'

// Ref date for testing: Nov 25, 2026.
const REF = new Date(2026, 10, 25)

describe('newarrivals.js', () => {
  it('calculates 30-day count correctly (53 items)', () => {
    expect(newArrivals(30, REF).length).toBe(53)
  })

  it('calculates 7-day count correctly (8 items)', () => {
    expect(newArrivals(7, REF).length).toBe(8)
  })

  it('calculates 14-day count correctly (23 items)', () => {
    expect(newArrivals(14, REF).length).toBe(23)
  })

  it('calculates all-time count correctly (53 items)', () => {
    expect(newArrivals('all', REF).length).toBe(53)
  })

  it('returns the distinct data tags (家電, 3C); "全部" is a UI prefix, not a tag', () => {
    const items = newArrivals(Number.POSITIVE_INFINITY, REF)
    const cats = deriveCategories(items)
    expect(cats).toContain('家電')
    expect(cats).toContain('3C')
    expect(cats.length).toBe(2)
  })

  it('handles empty data gracefully', () => {
    expect(newArrivals(30, REF).length).toBeGreaterThanOrEqual(0)
    expect(deriveCategories([]).length).toBe(0)
  })
})

describe('NewArrivalsMobile.vue', () => {
  it('renders with default 30-day period (53 items)', async () => {
    const wrapper = mount(NewArrivalsMobile, {
      props: { refDate: REF },
    })
    expect(wrapper.findAll('.na-card')).toHaveLength(53)
  })

  it('filters correctly when switching periods', async () => {
    const wrapper = mount(NewArrivalsMobile, {
      props: { refDate: REF },
    })

    // Start at 30 (default).
    expect(wrapper.findAll('.na-card')).toHaveLength(53)

    // Click 近 7 天.
    await wrapper.findAll('.na-period').at(0).trigger('click')
    expect(wrapper.findAll('.na-card')).toHaveLength(8)

    // Click 近 14 天.
    await wrapper.findAll('.na-period').at(1).trigger('click')
    expect(wrapper.findAll('.na-card')).toHaveLength(23)

    // Click 全部.
    await wrapper.findAll('.na-period').at(3).trigger('click')
    expect(wrapper.findAll('.na-card')).toHaveLength(53)
  })

  it('filters correctly by category (家電)', async () => {
    const wrapper = mount(NewArrivalsMobile, {
      props: { refDate: REF },
    })

    // Click 家電.
    await wrapper
      .findAll('.na-cat-chip')
      .filter((w) => w.text() === '家電')
      .at(0)
      .trigger('click')
    expect(wrapper.findAll('.na-card')).toHaveLength(26)

    // Click 全部.
    await wrapper
      .findAll('.na-cat-chip')
      .filter((w) => w.text() === '全部')
      .at(0)
      .trigger('click')
    expect(wrapper.findAll('.na-card')).toHaveLength(53)
  })

  it('shows empty state for no results', async () => {
    // A date 10 years in the future.
    const futureDate = new Date(2036, 0, 1)
    const wrapper = mount(NewArrivalsMobile, {
      props: { refDate: futureDate },
    })

    expect(wrapper.find('.na-empty').exists()).toBe(true)
    expect(wrapper.findAll('.na-card')).toHaveLength(0)
  })
})
