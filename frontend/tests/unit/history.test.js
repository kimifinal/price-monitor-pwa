// Guards for the app-side loader that turns /api payloads (or the baked-in
// snapshot) into renderable movement cards. These are the "renders a movement
// card" assertions the offline PWA needs without a live browser.
import { describe, it, expect } from 'vitest'
import {
  mapItem,
  cardsFromHistory,
  loadLiveHistory,
  SNAPSHOT_PATHS,
} from '../../src/lib/history.js'
import { sparkPath } from '../../src/lib/monitor.js'
import costcoSnapshot from '../../public/snapshot/costco-history.json'

describe('mapItem', () => {
  it('drops junk and non-object items', () => {
    expect(mapItem(null, 'costco')).toBeNull()
    expect(mapItem(42, 'costco')).toBeNull()
    expect(mapItem('nope', 'costco')).toBeNull()
  })

  it('maps snake_case backend metrics to the camelCase card shape', () => {
    const card = mapItem({
      sku: '149699',
      name: 'ANKER 67W',
      tag: '3C',
      current: 1069,
      low: 1069,
      high: 1375,
      drop_pct_from_high: 22.2,
      at_all_time_low: true,
      points: 6,
      series: [{ price: 1375 }, { price: 1069 }],
      currency: 'TWD',
      url: 'https://x',
    }, 'costco')
    expect(card.name).toBe('ANKER 67W')
    expect(card.current).toBe(1069)
    expect(card.metrics).toEqual({ points: 6, atAllTimeLow: true, dropPctFromHigh: 22.2 })
    expect(card.series).toEqual([1375, 1069])
    expect(card.currency).toBe('TWD')
    expect(card.url).toBe('https://x')
    expect(card.tag).toBe('3C')
  })

  it('accepts camelCase + numbers series and derives a sparkline', () => {
    const card = mapItem({
      name: 'X',
      current: 9,
      dropPctFromHigh: 5,
      atAllTimeLow: true,
      series: [11, 10, 9],
    }, 'costco')
    expect(card.series).toEqual([11, 10, 9])
    expect(sparkPath(card.series)).toContain('M') // draws a path
  })

  it('falls back through every dropPct source and defaults safely', () => {
    expect(mapItem({ name: 'A', drop_pct_from_high: 15 }, 'costco').metrics.dropPctFromHigh).toBe(15)
    expect(mapItem({ name: 'B', dropPctFromHigh: 8 }, 'costco').metrics.dropPctFromHigh).toBe(8)
    expect(mapItem({ name: 'C', verdict: { dropPct: 3 } }, 'costco').metrics.dropPctFromHigh).toBe(3)
    expect(mapItem({ name: 'D' }, 'costco').metrics.dropPctFromHigh).toBe(0)
  })

  it('derives points + atAllTimeLow defaults, filters junk series, omits empty series', () => {
    const c1 = mapItem({ name: 'P', atAllTimeLow: false, series: [1, 2, { price: 3 }, 'junk', NaN] }, 'costco')
    expect(c1.series).toEqual([1, 2, 3])
    expect(c1.metrics.points).toBe(3) // no explicit points -> derives from series.length ([1,2,3])
    const c2 = mapItem({ name: 'Q', points: 7, at_all_time_low: true }, 'costco')
    expect(c2.metrics.points).toBe(7)
    expect(c2.metrics.atAllTimeLow).toBe(true)
    const c3 = mapItem({ name: 'R', current: 5 }, 'costco') // no series
    expect(c3.series).toBeUndefined()
    expect(c3.metrics.atAllTimeLow).toBe(false)
  })

  it('uses sku as a name fallback when name is missing', () => {
    expect(mapItem({ sku: '3062725', current: 81 }, 'costco').name).toBe('3062725')
  })
})

describe('cardsFromHistory', () => {
  it('returns [] for non-objects / missing items array', () => {
    expect(cardsFromHistory(null)).toEqual([])
    expect(cardsFromHistory('x')).toEqual([])
    expect(cardsFromHistory({ items: null })).toEqual([])
    expect(cardsFromHistory({ count: 0, items: 'nope' })).toEqual([])
  })

  it('maps a bare item array and a {items} payload, filtering junk', () => {
    expect(cardsFromHistory([{ name: 'A', current: 1 }], 'costco')[0].name).toBe('A')
    const out = cardsFromHistory({ items: [{ name: 'A', current: 1 }, null, 5] }, 'costco')
    expect(out.length).toBe(1)
  })

  it('renders the COMMITTED costco snapshot into a movement card with a sparkline', () => {
    const cards = cardsFromHistory(costcoSnapshot, 'costco')
    expect(cards.length).toBeGreaterThan(0)
    // Every card is well-formed (metrics is computed even for single-obs SKUs).
    expect(cards.every((c) => c.metrics)).toBe(true)
    // Item order isn't guaranteed after a re-render, so don't assume cards[0] is the
    // rich one: find the first card that actually has a multi-point series + sparkline.
    const rich = cards.find((c) => c.series && c.series.length > 1)
    expect(rich).toBeTruthy()
    expect(sparkPath(rich.series)).toContain('M') // a real path, i.e. a rendered card
  })
})

describe('loadLiveHistory — live → snapshot fallback, never throws', () => {
  const ok = { count: 1, items: [{ name: 'Live', current: 1, points: 3, drop_pct_from_high: 10, at_all_time_low: true, series: [3, 2, 1] }] }

  it('uses the live API when it 200s', async () => {
    const calls = []
    const fetch = async (u) => {
      calls.push(u)
      return new Response(JSON.stringify(ok), { status: 200 })
    }
    const cards = await loadLiveHistory('http://h/', { fetch })
    expect(cards.length).toBe(1) // costco only now
    expect(calls.some((u) => u.includes('/api/costco/history'))).toBe(true)
  })

  it('falls back to the committed snapshot when the live API fails', async () => {
    const fetch = async (u) => {
      if (u.includes('/api/')) throw new Error('offline')
      if (u.includes(SNAPSHOT_PATHS.costco.snapshot)) return new Response(JSON.stringify(costcoSnapshot), { status: 200 })
      return new Response('nope', { status: 404 })
    }
    const cards = await loadLiveHistory('http://h/', { fetch })
    expect(cards.length).toBeGreaterThan(0)
  })

  it('returns [] for a total outage and when no fetch is available', async () => {
    const fetch = async () => {
      throw new Error('everything is down')
    }
    expect(await loadLiveHistory('http://h/', { fetch })).toEqual([])
    expect(await loadLiveHistory('http://h/', { fetch: undefined })).toEqual([])
  })

  it('degrades when a live 200 yields no cards', async () => {
    const fetch = async (u) => {
      if (u.includes('/api/')) return new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } })
      throw new Error('snapshot down')
    }
    // live returns empty -> tryEndpoint keeps falling to snapshot which is down => []
    expect(await loadLiveHistory('http://h/', { fetch })).toEqual([])
  })
})
