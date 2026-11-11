import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import WatchlistEditor from '../../src/components/WatchlistEditor.vue'
import {
  loadWatchlist,
  saveWatchlist,
  resetWatchlist,
  thresholdMet,
  findEntry,
  wouldAlert,
  cloneWatchlist,
  DEFAULT_WATCHLIST,
  WATCHLIST_KEY,
} from '../../src/lib/watchlist.js'

// =====================================================================
// lib/watchlist.js — the offline #4 gate (mirrors backend/watchlist.py)
// =====================================================================
describe('lib/watchlist.js — threshold gate', () => {
  it('target price reuses the SSOT rule (price <= target)', () => {
    expect(thresholdMet({ price: 80, dropPctFromHigh: 0 }, { sku: '1', threshold: { target: 100 } })).toBe(true)
    expect(thresholdMet({ price: 80 }, { sku: '1', threshold: { target: 75 } })).toBe(false)
  })

  it('min drop% compares against the sku own dropPctFromHigh', () => {
    expect(thresholdMet({ dropPctFromHigh: 20 }, { sku: '1', threshold: { min_drop_pct: 15 } })).toBe(true)
    expect(thresholdMet({ dropPctFromHigh: 10 }, { sku: '1', threshold: { min_drop_pct: 15 } })).toBe(false)
  })

  it('both fields are AND-ed, and an absent threshold is a no gate', () => {
    const m = { price: 80, dropPctFromHigh: 20 }
    expect(thresholdMet(m, { threshold: { target: 100, min_drop_pct: 15 } })).toBe(true)
    expect(thresholdMet(m, { threshold: { target: 75, min_drop_pct: 15 } })).toBe(false)
    expect(thresholdMet(m, {})).toBe(true)
    expect(thresholdMet(m, { threshold: {} })).toBe(true)
  })

  it('a missing price/drop fails its own field, junk is tolerated', () => {
    expect(thresholdMet({}, { threshold: { target: 10 } })).toBe(false)
    expect(thresholdMet({}, { threshold: { min_drop_pct: 10 } })).toBe(false)
    expect(thresholdMet({ price: 1 }, null)).toBe(true)
  })
})

describe('lib/watchlist.js — findEntry + wouldAlert (the gate)', () => {
  it('findEntry matches by sku as a string; unwatched => null', () => {
    const wl = [{ sku: '149699', threshold: { target: 1000 } }]
    expect(findEntry({ sku: '149699' }, wl)).not.toBeNull()
    expect(findEntry({ sku: 149699 }, wl)).not.toBeNull()
    expect(findEntry({ sku: '999' }, wl)).toBeNull()
    expect(findEntry({ sku: '1' }, null)).toBeNull()
  })

  it('an empty watchlist is silent; a null watchlist disables the gate', () => {
    const m = { sku: '1', price: 80, dropPctFromHigh: 20 }
    expect(wouldAlert(m, [])).toBe(false)          // AC5: empty => nothing fires
    expect(wouldAlert(m, null)).toBe(true)
    expect(wouldAlert(m, [{ sku: '1', threshold: { min_drop_pct: 15 } }])).toBe(true)
    expect(wouldAlert(m, [{ sku: '2', threshold: { min_drop_pct: 15 } }])).toBe(false) // not watched
  })
})

describe('lib/watchlist.js — offline persistence', () => {
  it('defaults to the static seed when localStorage is empty (fully offline)', () => {
    globalThis.localStorage.clear()
    expect(loadWatchlist()).toEqual(cloneWatchlist(DEFAULT_WATCHLIST))
  })

  it('saves and reloads through localStorage (no server round-trip)', () => {
    const entries = [{ sku: '7', name: 'X', threshold: { target: 5 } }]
    expect(saveWatchlist(entries)).toBe(true)
    expect(loadWatchlist().map((e) => e.sku)).toEqual(['7'])
  })

  it('resetWatchlist restores the seed', () => {
    saveWatchlist([{ sku: 'z' }])
    expect(resetWatchlist().length).toBe(DEFAULT_WATCHLIST.length)
  })
})

// =====================================================================
// components/WatchlistEditor.vue — DISPLAY + EDIT, offline
// =====================================================================
describe('WatchlistEditor.vue — display + offline edit', () => {
  it('displays the watchlist from a passed-in list, no network', async () => {
    globalThis.localStorage.clear()
    globalThis.fetch = vi.fn()
    const list = [{ sku: '149699', name: 'ANKER', threshold: { target: 1000 } }]
    const w = mount(WatchlistEditor, { props: { entries: list } })
    expect(w.find('[data-testid="watchlist-editor"]').exists()).toBe(true)
    expect(w.text()).toContain('149699')
    // name is shown in an editable field (display + edit in one place)
    expect(w.find('.we-name').element.value).toBe('ANKER')
    expect(w.findAll('.we-row')).toHaveLength(1)
    expect(globalThis.fetch).not.toHaveBeenCalled() // offline: no round-trip
    w.unmount()
  })

  it('renders the silent-default message for an EMPTY watchlist', () => {
    const w = mount(WatchlistEditor, { props: { entries: [] } })
    expect(w.find('[data-testid="we-empty"]').exists()).toBe(true)
    expect(w.findAll('.we-row')).toHaveLength(0)
  })

  it('adds an entry offline and persists to localStorage + emits change', async () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, { props: { entries: [] } })

    await w.find('.we-new-sku').setValue('5001')
    await w.find('.we-new-name').setValue('New Widget')
    // submit the form (a real-browser click submits it; jsdom doesn't, so fire
    // the submit event directly — the @submit.prevent handler is the same path)
    await w.find('.we-add').trigger('submit')

    expect(w.findAll('.we-row')).toHaveLength(1)
    expect(w.text()).toContain('5001')

    const emitted = w.emitted('change')
    expect(emitted).toBeTruthy()
    expect(emitted[emitted.length - 1][0].map((e) => e.sku)).toEqual(['5001'])
    // persisted offline (localStorage), not a server
    const saved = JSON.parse(globalThis.localStorage.getItem(WATCHLIST_KEY))
    expect(saved.map((e) => e.sku)).toEqual(['5001'])
  })

  it('refuses to add an empty sku and shows nothing', async () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, { props: { entries: [] } })
    await w.find('.we-add').trigger('submit') // empty sku
    expect(w.findAll('.we-row')).toHaveLength(0)
  })
})

describe('WatchlistEditor.vue — edit + remove, offline', () => {
  it('edits a per-item threshold and persists it', async () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, {
      props: { entries: [{ sku: '1', name: 'A', threshold: { target: 100 } }] },
    })
    await w.find('.we-target').setValue('42')
    await w.find('.we-target').trigger('change')
    expect(w.find('.we-target').element.value).toBe('42')
    const saved = JSON.parse(globalThis.localStorage.getItem(WATCHLIST_KEY))
    expect(saved[0].threshold.target).toBe(42)
  })

  it('removes an entry and persists the shrunk list', async () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, {
      props: { entries: [{ sku: '1', threshold: {} }, { sku: '2', threshold: {} }] },
    })
    expect(w.findAll('.we-row')).toHaveLength(2)
    await w.find('[data-testid="we-remove"]').trigger('click')
    expect(w.findAll('.we-row')).toHaveLength(1)
    const saved = JSON.parse(globalThis.localStorage.getItem(WATCHLIST_KEY))
    expect(saved.map((e) => e.sku)).toEqual(['2'])
  })
})

describe('WatchlistEditor.vue — probe (optional offline preview)', () => {
  it('shows a fire badge when a probe metric meets the gate', () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, {
      props: {
        entries: [{ sku: '1', name: 'A', threshold: { min_drop_pct: 15 } }],
        probe: [{ sku: '1', price: 80, dropPctFromHigh: 20 }],
      },
    })
    expect(w.text()).toContain('🔔 會觸發')
  })

  it('shows 待價 when a probe metric does not meet the gate', () => {
    globalThis.localStorage.clear()
    const w = mount(WatchlistEditor, {
      props: {
        entries: [{ sku: '1', name: 'A', threshold: { min_drop_pct: 90 } }],
        probe: [{ sku: '1', price: 80, dropPctFromHigh: 10 }],
      },
    })
    expect(w.text()).toContain('待價')
  })
})
