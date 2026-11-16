import { describe, it, expect } from 'vitest'
import { alertMessage } from '../../src/lib/monitor.js'

// #25 AC2 — alertMessage carries the TWD-prefixed target with NO decimals.
//
// alertMessage is a PRESENTATION function (it builds an alert string); it is NOT
// one of the decision functions, so its string format may change even though the
// DECISION logic (shouldAlert / priceVerdict / ...) must stay byte-unchanged
// (that's what monitor.test.js guards). Here we only assert the *display has no
// ".00" / decimal and shows the TWD prefix* — the exact strings the old code
// would have emitted ("$1069.00") must be gone.
describe('alertMessage — TWD display, no decimals (#25 AC2)', () => {
  it('shows the TWD-prefixed target as an integer, no ".00" and no "$"', () => {
    const msg = alertMessage({ name: 'X', price: 500, target: 1069 })
    expect(msg).toContain('TWD 1,069') // 1069 -> "1,069", prefixed, integer
    expect(msg).not.toContain('.00') // the old $1069.00 formatting is gone
    expect(msg).not.toMatch(/\.\d/) // no decimal digit anywhere
    expect(msg).not.toContain('$') // the legacy "$" + 2-decimal prefix is dropped
  })

  it('still carries the percent-below-target figure (decision text intact)', () => {
    const msg = alertMessage({ name: 'Chiikawa 徽章', price: 80, target: 100 })
    expect(msg).toContain('跌破目標價')
    expect(msg).toContain('Chiikawa 徽章')
    expect(msg).toContain('20%')
    expect(msg).not.toContain('.00')
  })
})
