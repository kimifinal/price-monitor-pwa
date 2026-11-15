import { describe, it, expect } from 'vitest'
import { formatTWD, moneyTWD } from '../../src/lib/format.js'

// #25 AC1 — TWD money-format SSOT (frontend/src/lib/format.js).
//
// These assertions PIN the exact output string rather than trusting the Node/
// jsdom locale engine (the spec warns the locale may default to en-US in CI).
// formatTWD returns a thousands-grouped INTEGER (TWD has no minor unit), so a
// 4-digit price is "1,069" — never "1,069.00".
describe('formatTWD — locale-grouped integer, zero decimals', () => {
  it('thousands-groups a 4-digit price (no ".00")', () => {
    expect(formatTWD(1069)).toBe('1,069')
  })

  it('renders "0" when the input is the number 0', () => {
    expect(formatTWD(0)).toBe('0')
  })

  it('renders "0" on null / undefined / NaN (falsy-coerced, no crash)', () => {
    expect(formatTWD(null)).toBe('0')
    expect(formatTWD(undefined)).toBe('0')
    expect(formatTWD(NaN)).toBe('0')
  })

  it('keeps grouping for a larger value with the same separator', () => {
    expect(formatTWD(12000)).toBe('12,000')
  })
})

describe('moneyTWD — TWD-prefixed display string', () => {
  it('prefixes the formatted amount with "TWD "', () => {
    expect(moneyTWD(1069)).toBe('TWD 1,069')
  })

  it('prefixes zero / null too', () => {
    expect(moneyTWD(0)).toBe('TWD 0')
    expect(moneyTWD(null)).toBe('TWD 0')
  })
})
