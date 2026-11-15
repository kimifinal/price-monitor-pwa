import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// #25 — loading skeleton + TWD source-level guard rails.
//
// Mirrors the #21/#22/#29 css-source-guard pattern: assert on the SOURCE that
// feeds the build (no build step, offline-safe, deterministic). Vite's
// production CSS minifier only strips whitespace/comments, so @keyframes,
// selectors and the var(--token) references survive byte-for-byte into
// dist/assets/*.css. Asserting on src/style.css is the pre-build SSOT.
//
// All assertions here are scoped: the "no raw hex" check is sliced to the
// appended #25 skeleton block only, because the :root token *definitions*
// legitimately hold hex (that is the token SSOT itself — never the point).
const here = dirname(fileURLToPath(import.meta.url))
const styleCssPath = join(here, '..', '..', 'src', 'style.css')
const styleCss = readFileSync(styleCssPath, 'utf8')

// The skeleton region is the appended #25 block at the END of style.css. Slice
// from its marker so the "no raw hex" check looks only at skeleton CSS, not the
// :root definitions (which hold hex by design). The "resolves" test below fails
// loudly if the marker is absent, so a wrong path can't silently pass.
const skeletonMarker = 'SKELETON-25'
const skeletonSlice = styleCss.slice(styleCss.indexOf(skeletonMarker))

// Recursively list *authored* source files so the toFixed(2) count scopes to
// real code (src/). node_modules is third-party and dist/coverage are generated
// artifacts — neither holds app-authored price formatting, so neither is scanned.
function walk(dir, acc = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    if (entry.isDirectory()) walk(p, acc)
    else if (entry.isFile() && /\.(js|jsx|vue|ts|tsx)$/.test(entry.name)) acc.push(p)
  }
  return acc
}
const srcSource = walk(join(here, '..', '..', 'src')).map((f) => readFileSync(f, 'utf8')).join('\n')

describe('skeleton source guard (#25)', () => {
  it('resolves src/style.css and the skeleton region (fails loudly on a wrong path)', () => {
    expect(styleCss.length).toBeGreaterThan(0)
    expect(typeof skeletonSlice).toBe('string')
    expect(skeletonSlice.length).toBeGreaterThan(50) // marker actually matched
    expect(skeletonSlice).toContain('@keyframes skeleton-shimmer')
    expect(skeletonSlice).toContain('.skeleton-card')
  })

  it('AC4a: defines @keyframes skeleton-shimmer', () => {
    expect(styleCss).toMatch(/@keyframes\s+skeleton-shimmer\b/)
  })

  it('AC4b: skeleton colours resolve through tokens, never raw hex', () => {
    // The skeleton region references var(--token)...
    expect(skeletonSlice).toMatch(/var\(\s*--/)
    // ...and carries no hard-coded colour. Scoping to the skeleton slice keeps
    // the :root token definitions (which legitimately hold hex) out of the check.
    expect(skeletonSlice).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })

  it('AC4c: #22 prefers-reduced-motion guard is intact (skeleton honours it)', () => {
    // The universal neutralizer must still exist, so the shimmer is disabled for
    // users who request reduced motion. A future edit that strips it turns red.
    expect(styleCss).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/)
    expect(styleCss).toMatch(/animation-duration:\s*0\.001ms/)
  })

  it('AC1b: no toFixed(2) anywhere in the authored source (TWD has no decimals)', () => {
    // Every price display now routes through the TWD formatter; the only
    // remaining toFixed in src/ is sparkPath's toFixed(1) (SVG coords, not a
    // price), which is explicitly NOT a price-decimals site.
    const toFixed2 = srcSource.match(/toFixed\s*\(\s*2\s*\)/g) || []
    expect(toFixed2.length).toBe(0)
  })

  it('AC1b: toFixed(1) in sparkPath survives (only the 2-decimal sites were removed)', () => {
    expect(srcSource).toMatch(/toFixed\s*\(\s*1\s*\)/)
  })
})
