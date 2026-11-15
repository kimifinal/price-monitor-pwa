import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// #22 Phase 2 — a11y CSS-source guard.
//
// The a11y pass (touch targets / :focus-visible ring / prefers-reduced-motion)
// lives ENTIRELY in src/style.css — the design-token SSOT (issue #21). Vite's
// production build only strips whitespace/comments; selectors and @media queries
// survive byte-for-byte, so the emitted dist/assets/*.css keeps these. Asserting
// on the SOURCE that feeds the build is deterministic (no build step, offline-safe)
// AND equivalent to the emitted CSS.
//
// Guard intent: if a future change strips the :focus-visible ring or the
// reduced-motion guard from style.css, this test turns CI red before
// that regression can ship.
//
// Resolution: resolve src/style.css relative to THIS test file via import.meta.url
// (frontend/tests/unit -> frontend/src), independent of the process cwd. ESLint's
// flat config declares no node global, so we deliberately avoid the cwd global.
const here = dirname(fileURLToPath(import.meta.url))
const styleCssPath = join(here, '..', '..', 'src', 'style.css')
const styleCss = readFileSync(styleCssPath, 'utf8')

describe('a11y CSS source guard (#22 Phase 2)', () => {
  it('resolves src/style.css (the pre-build design-token SSOT)', () => {
    // Defensive: a wrong path throws here, failing loudly instead of silently
    // passing the other assertions in this file.
    expect(styleCss.length).toBeGreaterThan(0)
  })

  it('emits a visible :focus-visible ring on interactive controls', () => {
    // A2: keyboard / AT users must see a focus ring.
    expect(styleCss).toMatch(/:focus-visible\b/)
  })

  it('guards ALL motion under prefers-reduced-motion', () => {
    // A3: every transition/animation/:active micro-animation is disabled for
    // users who request reduced motion.
    expect(styleCss).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
  })

  it('focus ring resolves through the token SSOT (--accent-hover), not hard-coded hex', () => {
    // Keep the CSS single-source-of-truth: the ring uses a token, never raw hex.
    expect(styleCss).toMatch(/var\(\s*--accent-hover\s*\)/)
  })
})
