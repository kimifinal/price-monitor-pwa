import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'

// #22 Phase 2 — a11y CSS-source guard.
//
// The a11y pass (touch targets / :focus-visible ring / prefers-reduced-motion)
// lives ENTIRELY in src/style.css — the design-token SSOT (issue #21). Vite's
// production build minifies by stripping whitespace/comments only; selectors and
// @media queries survive byte-for-byte, so the emitted dist/assets/*.css keeps
// these. Asserting on the SOURCE that feeds the build is therefore deterministic
// (no build step, offline-safe) AND equivalent to the emitted CSS.
//
// Guard intent: if a future change strips the :focus-visible ring or the
// reduced-motion guard from style.css, this test turns CI red before that
// regression can ship.
//
// Resolution: Vitest runs with cwd = the frontend/ package root (the dir
// holding both src/ and tests/), but a run may also start from the repo root,
// so try both and pick the first that exists.
const candidates = [
  path.join(process.cwd(), 'src', 'style.css'),
  path.join(process.cwd(), 'frontend', 'src', 'style.css'),
]
const styleCssPath = candidates.find((p) => existsSync(p)) || candidates[0]
const styleCss = readFileSync(styleCssPath, 'utf8')

describe('a11y CSS source guard (#22 Phase 2)', () => {
  it('resolves src/style.css (the pre-build design-token SSOT)', () => {
    // Defensive: if nothing resolved we must fail loudly, not silently pass.
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
