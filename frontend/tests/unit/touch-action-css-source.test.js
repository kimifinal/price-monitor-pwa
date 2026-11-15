import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// #29 — mobile touch-action CSS-source guard.
//
// touch-action: manipulation (bans iOS Safari double-tap-zoom but KEPT pan/scroll
// via 'manipulation', unlike 'none') lives ENTIRELY in src/style.css, applied to
// every interactive control through a GLOBAL (non-scoped) rule. Like the #22 a11y
// guard, Vite's production CSS minifier only strips whitespace/comments — selectors
// and the declaration survive byte-for-byte — so asserting on the SOURCE that feeds
// the build is deterministic (no build step, offline-safe) and equivalent to the
// emitted dist/assets/*.css.
//
// Guard intent: if a future change DROPS touch-action from the interactive controls,
// or HIDES it behind an @media (hover: hover)/(pointer) query that excludes touch
// devices, this test turns CI red before that regression can ship.
//
// Resolution: resolve src/style.css relative to THIS test file via import.meta.url
// (frontend/tests/unit -> frontend/src), independent of the process cwd. ESLint's
// flat config declares no node global, so we deliberately avoid process.cwd().
const here = dirname(fileURLToPath(import.meta.url))
const styleCssPath = join(here, '..', '..', 'src', 'style.css')
const styleCss = readFileSync(styleCssPath, 'utf8')

describe('touch-action CSS source guard (#29)', () => {
  it('resolves src/style.css (the pre-build design-token SSOT)', () => {
    // Defensive: a wrong path throws here, failing loudly instead of silently
    // passing the other assertions in this file.
    expect(styleCss.length).toBeGreaterThan(0)
  })

  it('declares touch-action: manipulation on a button-family control rule', () => {
    // AC1: the declaration must be present AND attached to a rule whose selector
    // list targets a <button> / [role='button'] / a[href] control — not some
    // unrelated selector.
    expect(styleCss).toMatch(/touch-action:\s*manipulation/)
    // Prove it sits inside a button-family rule block (selector → { … touch-action … }).
    const inControlRule =
      /(?:button|\[role=\s*'?button'?\s*]|a\[href\])[^{]*\{\s*[^}]*touch-action:\s*manipulation/s
    expect(styleCss).toMatch(inControlRule)
  })

  it('does NOT gate touch-action behind a hover/pointer media query', () => {
    // AC2: touch-action must apply on touch devices directly, so it must NOT live
    // inside @media (hover: hover|any) / @media (pointer: fine|any), which exclude
    // touch input. style.css defines neither; assert that so a later change cannot
    // smuggle the rule behind a hover-only guard.
    expect(styleCss).not.toMatch(/@media\s*\(\s*hover:/)
    expect(styleCss).not.toMatch(/@media\s*\(\s*pointer:/)
  })

  it('adds no raw hex to the touch-action rule (zero visual drift from #21/#22)', () => {
    // AC3 guard: the change is a pure declaration — the touch-action rule must carry
    // no colour value. Extract the rule block that owns the declaration and assert
    // it holds no hex literal, so a future "recolour the buttons here" can't sneak
    // in without flipping this red.
    const touchRule = styleCss.match(
      /(?:button|\[role=\s*'?button'?\s*]|a\[href\])[^{]*\{\s*[^}]*touch-action:\s*manipulation[^}]*\}/s,
    )
    expect(touchRule).not.toBeNull()
    expect(touchRule[0]).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})
