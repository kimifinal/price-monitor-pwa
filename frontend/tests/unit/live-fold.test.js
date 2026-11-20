import { describe, it, expect } from 'vitest'
import {
  isTriggered,
  isNearLow,
  filterLive,
  foldCards,
  FOLD_LIMIT,
} from '../../src/lib/live-fold.js'

// Build a live card of a given verdict. priceVerdict (SSOT in monitor.js) maps the
// metrics → verdict, mirroring backend/models.py:price_verdict:
//   all_time_low = atAllTimeLow short-circuits any drop
//   good_deal    = not all-time-low AND drop >= 15
//   near_high    = not all-time-low AND drop <= 5
//   stable       = not all-time-low AND 5 < drop < 15
//   unknown      = no points / no metrics
const card = (metrics, extra = {}) => ({
  name: 'X',
  current: 1,
  metrics,
  url: '',
  source: 'costco',
  currency: '',
  tag: 'costco',
  ...extra,
})
const allTimeLow = (v = 30) => card({ points: 6, atAllTimeLow: true, dropPctFromHigh: v })
const goodDeal = (v = 20) => card({ points: 6, atAllTimeLow: false, dropPctFromHigh: v })
const nearHigh = (v = 3) => card({ points: 6, atAllTimeLow: false, dropPctFromHigh: v })
const stable = (v = 8) => card({ points: 6, atAllTimeLow: false, dropPctFromHigh: v })
const unknown = () => card({ points: 0, atAllTimeLow: false, dropPctFromHigh: 0 })

describe('isTriggered (all_time_low ∪ good_deal)', () => {
  it('is true at an all-time low regardless of drop size', () => {
    expect(isTriggered(allTimeLow(30))).toBe(true)
    expect(isTriggered(allTimeLow(1))).toBe(true) // atAllTimeLow short-circuits
  })

  it('is true for a good deal (>= 15% below the high)', () => {
    expect(isTriggered(goodDeal(20))).toBe(true)
    expect(isTriggered(goodDeal(15))).toBe(true) // exactly 15 counts
  })

  it('is false for stable / near_high / unknown', () => {
    expect(isTriggered(stable(8))).toBe(false)
    expect(isTriggered(nearHigh(3))).toBe(false)
    expect(isTriggered(unknown())).toBe(false)
  })

  it('is false on the 15% lower boundary (14.9 => stable)', () => {
    expect(isTriggered(goodDeal(14.9))).toBe(false)
  })

  it('defends against junk (null / missing metrics / non-object)', () => {
    expect(isTriggered(null)).toBe(false)
    expect(isTriggered(undefined)).toBe(false)
    expect(isTriggered({})).toBe(false)
    expect(isTriggered({ name: 'no metrics' })).toBe(false)
  })
})

describe('isNearLow (good_deal only — a strict subset of isTriggered)', () => {
  it('is true for a good deal', () => {
    expect(isNearLow(goodDeal(20))).toBe(true)
    expect(isNearLow(goodDeal(15))).toBe(true)
  })

  it('is FALSE for all_time_low — near-low is a subset, so an all-time low is not "near low"', () => {
    expect(isNearLow(allTimeLow(30))).toBe(false)
  })

  it('is false for stable / near_high / unknown', () => {
    expect(isNearLow(stable(8))).toBe(false)
    expect(isNearLow(nearHigh(3))).toBe(false)
    expect(isNearLow(unknown())).toBe(false)
  })

  it('is false on the 15% lower boundary (14.9 => stable, not good_deal)', () => {
    expect(isNearLow(goodDeal(14.9))).toBe(false)
  })

  it('defends against junk', () => {
    expect(isNearLow(null)).toBe(false)
    expect(isNearLow({})).toBe(false)
  })

  it('near-low results are always a subset of triggered results', () => {
    const cards = [allTimeLow(), goodDeal(20), goodDeal(30), stable(), nearHigh(), unknown()]
    for (const c of cards) {
      if (isNearLow(c)) expect(isTriggered(c)).toBe(true)
    }
  })
})

describe('filterLive (3 states)', () => {
  const cards = [allTimeLow(), goodDeal(20), goodDeal(30), stable(), nearHigh(), unknown()]

  it('`all` returns every card (in order)', () => {
    expect(filterLive(cards, 'all')).toHaveLength(6)
    expect(filterLive(cards)).toHaveLength(6) // default filter is `all`
  })

  it('`triggered` keeps only all_time_low ∪ good_deal', () => {
    const out = filterLive(cards, 'triggered')
    expect(out).toHaveLength(3)
    expect(out.map((c) => c.metrics.atAllTimeLow || c.metrics.dropPctFromHigh)).toEqual(
      [true, 20, 30],
    )
    expect(out).not.toContain(expect.objectContaining({ metrics: cards[3].metrics }))
  })

  it('`near-low` keeps only good_deal (a subset of triggered)', () => {
    const out = filterLive(cards, 'near-low')
    expect(out).toHaveLength(2) // the two good_deal cards; the all_time_low is excluded
    for (const c of out) expect(isNearLow(c)).toBe(true)
    expect(out.length).toBeLessThanOrEqual(filterLive(cards, 'triggered').length)
  })

  it('an unknown filter key falls back to `all`', () => {
    expect(filterLive(cards, 'bogus')).toHaveLength(6)
    expect(filterLive(cards, undefined)).toHaveLength(6)
  })

  it('non-array input yields []', () => {
    expect(filterLive(null)).toEqual([])
    expect(filterLive(undefined)).toEqual([])
    expect(filterLive('not-array')).toEqual([])
    expect(filterLive({})).toEqual([])
  })

  it('empty input yields [] for every filter', () => {
    expect(filterLive([])).toEqual([])
    expect(filterLive([], 'triggered')).toEqual([])
    expect(filterLive([], 'near-low')).toEqual([])
  })

  it('does not mutate the input array', () => {
    const before = [...cards]
    filterLive(cards, 'triggered')
    expect(cards).toStrictEqual(before)
  })
})

describe('foldCards (collapse beyond FOLD_LIMIT)', () => {
  it('FOLD_LIMIT is 6', () => {
    expect(FOLD_LIMIT).toBe(6)
  })

  it('collapses a 52-card set to 6 visible + 46 folded (the issue #23 acceptance case)', () => {
    const cards = Array.from({ length: 52 }, (_, i) => ({ name: `#${i}` }))
    const r = foldCards(cards)
    expect(r.total).toBe(52)
    expect(r.visible).toHaveLength(6)
    expect(r.foldedCount).toBe(46)
  })

  it('expanded=true shows every card, nothing folded', () => {
    const cards = Array.from({ length: 52 }, (_, i) => ({ i }))
    const r = foldCards(cards, { expanded: true })
    expect(r.visible).toHaveLength(52)
    expect(r.foldedCount).toBe(0)
    expect(r.total).toBe(52)
  })

  it('does not fold when the set is exactly at the limit', () => {
    const cards = Array.from({ length: 6 }, (_, i) => ({ i }))
    const r = foldCards(cards)
    expect(r.visible).toHaveLength(6)
    expect(r.foldedCount).toBe(0)
  })

  it('does not fold when below the limit', () => {
    const cards = Array.from({ length: 3 }, (_, i) => ({ i }))
    const r = foldCards(cards)
    expect(r.visible).toHaveLength(3)
    expect(r.foldedCount).toBe(0)
  })

  it('empty input yields an empty fold result', () => {
    const r = foldCards([])
    expect(r).toEqual({ visible: [], foldedCount: 0, total: 0 })
  })

  it('non-array input yields an empty fold result', () => {
    expect(foldCards(null)).toEqual({ visible: [], foldedCount: 0, total: 0 })
    expect(foldCards(undefined)).toEqual({ visible: [], foldedCount: 0, total: 0 })
    expect(foldCards('x')).toEqual({ visible: [], foldedCount: 0, total: 0 })
  })

  it('honours a custom limit', () => {
    const cards = Array.from({ length: 10 }, (_, i) => i)
    const r = foldCards(cards, { limit: 4 })
    expect(r.visible).toHaveLength(4)
    expect(r.foldedCount).toBe(6)
    expect(r.total).toBe(10)
  })

  it('does not mutate the input', () => {
    const cards = Array.from({ length: 10 }, (_, i) => i)
    const before = [...cards]
    foldCards(cards)
    expect(cards).toStrictEqual(before)
  })
})
