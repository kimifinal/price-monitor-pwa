import { describe, it, expect } from 'vitest'
import {
  shouldAlert,
  percentBelowTarget,
  sortByUrgency,
  alertMessage,
  alertedItems,
} from '../../src/lib/monitor.js'

describe('shouldAlert', () => {
  it('alerts when price is exactly at target', () => {
    expect(shouldAlert({ price: 100, target: 100 })).toBe(true)
  })

  it('alerts when price is below target', () => {
    expect(shouldAlert({ price: 90, target: 100 })).toBe(true)
  })

  it('does not alert when price is above target', () => {
    expect(shouldAlert({ price: 120, target: 100 })).toBe(false)
  })

  it('returns false on null/undefined input', () => {
    expect(shouldAlert(null)).toBe(false)
    expect(shouldAlert(undefined)).toBe(false)
  })

  it('returns false on non-numeric price', () => {
    expect(shouldAlert({ price: 'abc', target: 100 })).toBe(false)
    expect(shouldAlert({ price: undefined, target: 100 })).toBe(false)
  })

  it('returns false when target is NaN', () => {
    expect(shouldAlert({ price: NaN, target: 100 })).toBe(false)
    expect(shouldAlert({ price: 100, target: NaN })).toBe(false)
  })

  it('returns false on Infinity price', () => {
    expect(shouldAlert({ price: Infinity, target: 100 })).toBe(false)
  })
})

describe('percentBelowTarget', () => {
  it('computes percent below target for a drop', () => {
    // target 100, price 80 => 20% below
    expect(percentBelowTarget({ price: 80, target: 100 })).toBeCloseTo(20, 5)
  })

  it('returns 0 when target is 0 (avoid divide-by-zero)', () => {
    expect(percentBelowTarget({ price: 50, target: 0 })).toBe(0)
  })

  it('returns 0 on null input', () => {
    expect(percentBelowTarget(null)).toBe(0)
    expect(percentBelowTarget(undefined)).toBe(0)
  })

  it('returns 0 when price is non-numeric', () => {
    expect(percentBelowTarget({ price: null, target: 100 })).toBe(0)
    expect(percentBelowTarget({ target: 100 })).toBe(0)
  })
})

describe('sortByUrgency', () => {
  it('sorts items closest to/below target first', () => {
    const items = [
      { id: 'a', name: 'A', price: 150, target: 100 }, // -50% (above, least urgent)
      { id: 'b', name: 'B', price: 50, target: 100 }, // +50% (below, most urgent)
      { id: 'c', name: 'C', price: 100, target: 100 }, // 0%
    ]
    const sorted = sortByUrgency(items)
    expect(sorted.map((i) => i.id)).toEqual(['b', 'c', 'a'])
  })

  it('does not mutate the input array', () => {
    const items = [
      { id: 'a', name: 'A', price: 150, target: 100 },
      { id: 'b', name: 'B', price: 50, target: 100 },
    ]
    const original = [...items]
    sortByUrgency(items)
    expect(items).toStrictEqual(original)
  })

  it('returns empty array on non-array input', () => {
    expect(sortByUrgency(null)).toEqual([])
    expect(sortByUrgency(undefined)).toEqual([])
    expect(sortByUrgency('foo')).toEqual([])
  })
})

describe('alertMessage', () => {
  it('returns empty string on null input', () => {
    expect(alertMessage(null)).toBe('')
    expect(alertMessage(undefined)).toBe('')
  })

  it('returns below-target message when alerting', () => {
    const msg = alertMessage({ name: 'Chiikawa 徽章', price: 80, target: 100 })
    expect(msg).toContain('跌破目標價')
    expect(msg).toContain('Chiikawa 徽章')
    expect(msg).toContain('20%')
  })

  it('uses 未命名 when name is missing', () => {
    const msg = alertMessage({ price: 80, target: 100 })
    expect(msg).toContain('未命名')
  })

  it('returns above-target message when not alerting', () => {
    const msg = alertMessage({ name: 'X', price: 120, target: 100 })
    expect(msg).toContain('尚未到價')
    expect(msg).toContain('X')
  })
})

describe('alertedItems', () => {
  it('returns only items that should alert', () => {
    const items = [
      { id: '1', price: 80, target: 100 }, // alerts
      { id: '2', price: 120, target: 100 }, // doesn't
      { id: '3', price: 100, target: 100 }, // at target, alerts
    ]
    const alerts = alertedItems(items)
    expect(alerts.map((i) => i.id)).toEqual(['1', '3'])
  })

  it('returns empty array on non-array input', () => {
    expect(alertedItems(null)).toEqual([])
    expect(alertedItems('foo')).toEqual([])
  })
})
