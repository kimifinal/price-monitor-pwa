# pipeline/a11y-touch.md — #22 Phase 2: 可及性 (a11y) + mobile 觸控目標

Issue #22 · Variant B (1 Coder) · branch `feature/a11y-touch` off `e1e5858` (fresh master).
Depends on #21 (the `:root` token system is now live — focus/transition styles reference it).

## Goal
Make the PWA mobile-accessible per design.md §6: touch targets ≥ 44×44px, a visible
focus ring, motion respects `prefers-reduced-motion`, every control has an accessible
name, and body/small text meets WCAG AA. **This is a deliberate a11y improvement —
visual size WILL change (bigger touch targets); that is intended, unlike #21.**

## Context (from the §6 audit, 2026-11-14)
- 10-11 interactive controls are all < 44×44px (watchlist `we-btn` ≈ 29px tall,
  `加入追蹤` ≈ 37px). WCAG 2.5.5 / Apple HIG want 44pt.
- No `:focus-visible` styling (keyboard/AT users get no ring).
- No `@media (prefers-reduced-motion)` guard over the existing `:active`/transition
  micro-animations (`transform: scale` on button press etc.).
- Most controls already use real `<button>`; aria-label is absent on icon/short-text
  controls (only the sparkline svg has one).
- `--muted` (#555555) and `--text-3` (#8a86a8) on `--bg` (#0f0d13) — verify AA (4.5:1).

## Acceptance (must all hold)
- A1. **Touch targets**: every interactive control (`<button>`, interactive `a`,
      `[role=button]`, the import/export chips) has effective hit area ≥ 44×44px
      (use `min-height/min-width: 44px` OR padding that achieves it; keep visual size
      reasonable — the hit area, not necessarily the painted size, must be ≥44).
- A2. **`:focus-visible`**: all interactive elements show a visible focus outline
      (`:focus-visible { outline: 2px solid var(--accent-hover); outline-offset: 2px; }`
      or equivalent using existing tokens).
- A3. **`prefers-reduced-motion`**: every `transition`/`animation`/`:active`
      micro-animation is wrapped so it is disabled under
      `@media (prefers-reduced-motion: reduce)`.
- A4. **Accessible names**: every icon-only / short-text control has an `aria-label`
      (or visible text); audit and fill the gaps.
- A5. **Contrast**: `--muted`/`--text-3` on `--bg` ≥ 4.5:1. If a token already fails,
      adjust the TOKEN value (in `style.css`, keeping the semantic name) — do NOT
      hard-code per component. Log any token value you changed and why.
- A6. **No regression**: all existing frontend unit tests stay green; add a small
      CSS-source guard test that asserts the emitted CSS contains `:focus-visible`
      AND `prefers-reduced-motion` (so a future removal fails CI). Do not touch
      `src/lib/`, template behavior, data-* attrs, or the a11y-relevant selectors.
- A7. **CI green** (frontend job incl. the SSOT grep-guard + backend + secrets-guard).

## Hard constraints for the Coder
- Pure-CSS + minimal semantic HTML only. NO logic / NO `src/lib/` / NO test-assertion
  weakening / NO new npm deps.
- Use the existing `--` tokens (incl. `--accent-hover` if you add it) — keep the CSS SSOT
  clean. Any NEW token goes into `style.css` `:root`, not inline hex in components
  (the CI grep-guard will FAIL on raw hex in `.vue`).
- Leave changes UNSTAGED; do NOT commit/push/PR; do NOT `git clean` / delete untracked
  (design.md + pipeline/ must survive).
- zh-TW only; any new user-visible strings are Chinese, no simplified chars.
- Verify by running the full frontend test suite AND by grepping the EMITTED CSS
  (build → `dist/assets/*.css`) for `:focus-visible` and `prefers-reduced-motion`,
  because computed-style can be unreliable in headless Chromium. Report what you
  actually ran; do not claim numbers you didn't run.

## Variant / gate
- Variant B (bounded a11y pass, not a multi-solution hard problem).
- Deterministic anchor = CI (no verify.py in this repo). Orchestrator reproduces the
  full frontend suite + reads `actions/runs?head_sha=…`. Coder's self-report = a LEAD.
