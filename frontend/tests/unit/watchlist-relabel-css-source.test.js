import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

// #24 — layered watchlist naming source-guard (component-source guard).
//
// One page held TWO "watchlist" concepts that shared the SAME 🎯 icon:
//   • the user's MANUAL list  — App.vue `追蹤中（N）`
//   • the system's gate seed  — App.vue `🎯 個人化通知門檻` + editor `🎯 個人化追蹤（N）`
// So a user could not tell "I'm tracking an item" from "the system's default alert
// gate". #24 splits them by icon: 🎯 = the user's MANUAL target list,
// ⚙ = the SYSTEM's AUTO threshold gate. The copy lives ENTIRELY in the two .vue
// templates (+ the editor's top comment), so asserting on the SOURCE that feeds the
// build is deterministic (no build step, offline-safe), like the #29 touch-action
// guard — Vite only minifies CSS here, never these template strings, so they survive
// byte-for-byte.
//
// Guard intent: if a future change re-introduces the old words (`追蹤中` /
// `🎯 個人化…`) — or reuses 🎯 for the gate (icon duplication) — this test turns CI
// red before that regression can ship.
//
// Resolution: resolve the two .vue sources relative to THIS test file via
// import.meta.url (frontend/tests/unit -> src / src/components), independent of the
// process cwd. ESLint's flat config declares no node global, so we deliberately avoid
// process.cwd().
const here = dirname(fileURLToPath(import.meta.url))
const appVuePath = join(here, '..', '..', 'src', 'App.vue')
const editorVuePath = join(here, '..', '..', 'src', 'components', 'WatchlistEditor.vue')
const appVue = readFileSync(appVuePath, 'utf8')
const editorVue = readFileSync(editorVuePath, 'utf8')

// Count literal, non-overlapping occurrences of `needle` in `hay` (0 when absent).
// Split-on-literal avoids regex metachar / unicode pitfalls with the CJK + emoji labels.
function count(hay, needle) {
  return hay.split(needle).length - 1
}

describe('watchlist relabel source guard (#24)', () => {
  it('resolves both .vue sources (the user-facing UI SSOT)', () => {
    // Defensive: a wrong path throws/empty here, failing loudly instead of silently
    // passing the assertions that follow in this file.
    expect(appVue.length).toBeGreaterThan(0)
    expect(editorVue.length).toBeGreaterThan(0)
  })

  it('AC1a: App.vue manual list header carries the target icon + 手動追蹤 text', () => {
    // #40: the manual list owns the "target" line-icon (it was the 🎯 emoji).
    // The discriminator moved from the emoji CHAR to the icon NAME — 1:1 semantics.
    expect(appVue).toContain('name="target"')
    expect(appVue).toContain('手動追蹤')
  })

  it('AC1b/AC1c: gate header carries the gear icon + 自動門檻 Gate in BOTH files', () => {
    expect(appVue).toContain('name="gear"')
    expect(appVue).toContain('自動門檻 Gate')
    expect(editorVue).toContain('name="gear"')
    expect(editorVue).toContain('自動門檻 Gate')
  })

  it('AC1d: the old words (追蹤中 / 個人化) are gone from BOTH files', () => {
    // No regression back to the pre-#24 copy in either host page or editor.
    expect(appVue).not.toContain('追蹤中')
    expect(editorVue).not.toContain('追蹤中')
    expect(appVue).not.toContain('個人化')
    expect(editorVue).not.toContain('個人化')
  })

  it('AC2: target icon not duplicated — manual=App only, gate uses gear in both', () => {
    // The anti-duplication core of #24, now in icon NAME instead of the emoji char:
    // the manual "target" icon lives exactly once in App.vue and nowhere in the
    // editor; the gate's "gear" icon is in BOTH. A future change that re-stamps a
    // target icon on a gate header (or puts one manual icon on two surfaces) flips
    // this red — same invariant, emoji-free.
    expect(count(appVue, 'name="target"')).toBe(1)
    expect(count(editorVue, 'name="target"')).toBe(0)
    expect(count(appVue, 'name="gear"')).toBeGreaterThanOrEqual(1)
    expect(count(editorVue, 'name="gear"')).toBeGreaterThanOrEqual(1)
  })

  it('AC3 #40: App.vue section headings carry line icons, not emoji', () => {
    // The sloplint 30a migration: the headlined section titles are now icon + text,
    // no raw emoji. Emoji are NOT banned project-wide — the editor's we-fire probe
    // and code comments stay as-is — this only checks the App.vue headings.
    const EMOJI = ['🔔', '🎯', '📊', '📡', '⚙']
    for (const e of EMOJI) expect(appVue.includes(e)).toBe(false)
  })
})
