import { describe, it, expect, beforeEach, vi } from 'vitest'
import { loadItems, saveItems, setCookie, STORAGE_KEY } from '../../src/lib/storage.js'

describe('loadItems', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('returns empty array when nothing stored', () => {
    expect(loadItems()).toEqual([])
  })

  it('parses stored JSON', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([{ id: '1', name: 'X' }]))
    expect(loadItems()).toEqual([{ id: '1', name: 'X' }])
  })

  it('returns empty array on corrupt JSON', () => {
    window.localStorage.setItem(STORAGE_KEY, 'not json{{{')
    expect(loadItems()).toEqual([])
  })

  it('returns empty array when stored value is not an array', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ foo: 'bar' }))
    expect(loadItems()).toEqual([])
  })
})

describe('saveItems', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('returns true and persists items', () => {
    const items = [{ id: '1', name: 'X', target: 100 }]
    expect(saveItems(items)).toBe(true)
    expect(loadItems()).toEqual(items)
  })

  it('returns false when localStorage write fails', () => {
    const spy = vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    expect(saveItems([{ id: '1' }])).toBe(false)
    spy.mockRestore()
  })
})

describe('setCookie', () => {
  it('returns true and sets a cookie', () => {
    expect(setCookie('alert', '1', 10000)).toBe(true)
    expect(document.cookie).toContain('alert=1')
  })

  it('encodes the cookie value', () => {
    expect(setCookie('k', 'a b/c', 1000)).toBe(true)
    expect(document.cookie).toContain('k=a%20b%2Fc')
  })
})
