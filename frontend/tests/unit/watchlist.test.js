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
// lib/watchlist.js — #11: portable export/import lib
// =====================================================================
import {
  serializeWatchlist,
  deserializeWatchlist,
  buildExportBlob,
} from '../../src/lib/watchlist.js'

describe('lib/watchlist.js — #11: serialize / deserialize / export', () => {
  it('(a) serialize→deserialize roundtrip: same skus / names / thresholds', () => {
    const input = [
      { sku: '149699', name: 'ANKER', threshold: { target: 1069 } },
      { sku: '153876', name: 'JBL', threshold: { min_drop_pct: 15 } },
      { sku: '161367' }, // no threshold
    ]
    const json = serializeWatchlist(input)
    const { entries, errors } = deserializeWatchlist(json)
    expect(errors).toEqual([])
    expect(entries.map((e) => e.sku).sort()).toEqual(['149699', '153876', '161367'])
    const bySku = Object.fromEntries(entries.map((e) => [e.sku, e]))
    expect(bySku['149699'].name).toBe('ANKER')
    expect(bySku['149699'].threshold).toEqual({ target: 1069 })
    expect(bySku['153876'].threshold).toEqual({ min_drop_pct: 15 })
    expect(bySku['161367'].threshold).toBeUndefined()
  })

  it('(b) serialize dedups by sku, last occurrence wins', () => {
    const input = [
      { sku: '999', name: 'first', threshold: { target: 1 } },
      { sku: '999', name: 'second', threshold: { target: 2 } },
    ]
    const json = serializeWatchlist(input)
    const entries = deserializeWatchlist(json).entries
    expect(entries).toHaveLength(1)
    expect(entries[0]).toMatchObject({ sku: '999', name: 'second', threshold: { target: 2 } })
  })

  it('(c) import entry missing sku → skipped, error recorded', () => {
    const json = JSON.stringify([{ name: 'no sku' }, { sku: '1', name: 'ok' }])
    const { entries, errors } = deserializeWatchlist(json)
    expect(errors).toHaveLength(1)
    expect(errors[0].error).toContain('缺少 sku')
    expect(entries).toHaveLength(1)
    expect(entries[0].sku).toBe('1')
  })

  it('(d) threshold with bad key → silently dropped to {}', () => {
    const json = JSON.stringify([{ sku: '1', threshold: { foo: 1, target: 100 } }])
    const { entries, errors } = deserializeWatchlist(json)
    expect(errors).toEqual([])
    expect(entries[0].threshold).toEqual({ target: 100 })
  })

  it('(e) empty JSON array → empty entries, no errors', () => {
    const { entries, errors } = deserializeWatchlist('[]')
    expect(entries).toEqual([])
    expect(errors).toEqual([])
  })

  it('(f) mixed valid + invalid → valid imported, bad recorded in errors', () => {
    const json = [
      { sku: '1', name: 'ok' },
      'not-an-object',
      {}, // no sku
      { sku: '3', name: 'also-ok', threshold: { target: 50 } },
    ]
    const { entries, errors } = deserializeWatchlist(JSON.stringify(json))
    expect(entries.map((e) => e.sku).sort()).toEqual(['1', '3'])
    expect(errors).toHaveLength(2) // one for 'not-an-object', one for '{}' (missing sku)
  })

  it('(g) serializeWatchlist output is valid JSON with trailing newline', () => {
    const json = serializeWatchlist([{ sku: '1', name: 'X' }])
    expect(json.endsWith('\n')).toBe(true)
    const parsed = JSON.parse(json)
    expect(parsed).toHaveLength(1)
    expect(parsed[0].sku).toBe('1')
  })

  it('buildExportBlob returns null when Blob global is absent (SSR safe)', () => {
    const savedBlob = globalThis.Blob
    delete globalThis.Blob
    expect(buildExportBlob([{ sku: '1' }])).toBeNull()
    globalThis.Blob = savedBlob // restore
  })
})
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
