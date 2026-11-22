# pipeline/ui-token-system.md — Phase 1 CSS Design Token System

Issue #21 · Variant B (1 Coder + 1 adversarial Reviewer + CI as deterministic anchor)
· Branch `feature/ui-token-system` off `master` @ 4663e88 · Pure-CSS restyle.

## Goal
Establish the CSS **single source of truth**: a `:root` token layer so that every
color / spacing / radius in the UI references a semantic `var(--…)`, not a
hard-coded value. Zero visual change (token value == the hex it replaces). Plus a
root/html `font-family` fix and a CI guard that forbids raw hex in components.

## Acceptance (must all hold)
- A1. `frontend/src/style.css` exists: `@layer tokens, base, components, utilities;`
      and `:root` holds semantic tokens (color / type scale / spacing scale /
      radius scale / accent / status + any per-control color used).
- A2. `frontend/src/main.js` imports `style.css`.
- A3. **Zero raw 6-digit hex** (`#rrggbb`) remains in `frontend/src/**/*.vue`
      (all replaced by `var(--token)`). `style.css` is exempt (it *defines* them).
- A4. root / html `font-family` fixed so `body` no longer falls back to Times
      (serif). `html { font-family: ... }`, and `body`/`.app` extend it.
- A5. **No template / behavior / `src/lib/` change.** All `data-*` attrs and test
      selectors unchanged. All 99 frontend unit tests stay green.
- A6. CI green: `ci.yml` + `refresh-costco.yml` all checks `success`.
- A7. CI grep guard added: a step that FAILS on raw hex in `frontend/src/**/*.vue`
      (excluding `style.css`), so the SSOT is defended going forward.

## Token set (semantic — `:root` values == the current hex, so visual diff ≈ 0)
Color: --bg #0f0d13 · --surface #141218 · --surface-1 #1b1830 · --surface-2 #0f0d18
 · --border #2a2740 · --border-2 #3a3560 · --text #efeaff · --text-2 #b0a8c8
 · --text-3 #8a86a8 · --muted #555555 · --accent #4a3f7a · --accent-2 #3a3560
 · --success #4caf50 · --success-tx #8ae0b0 · --good-deal #8bc34a · --warn #e6a23c
 · --danger #e07a7a · --danger-b #4a3345 · --sku #f0c000 · --link #8fb4ff
 (WatchlistEditor extra controls: --export-b / --export-bg / --import-b / --import-bg
  — map #3a6a5a / #1a3a2a / #6a3a5a / #3a1a3a / #e0a0c8 to NEW named tokens so the
  grep guard passes; keep the value == the exact hex currently there.)
Scale (add as tokens, then reference): --sp-1..8 (4/8/12/16/24/32/48px),
--radius / --radius-sm / --radius-lg / --radius-pill (10/8/16/999), type scale.

## Hard constraints for the Coder
- PURE CSS: change NO `<template>`, NO `<script>` logic, NO `src/lib/`, NO tests'
  assertions. Only `<style>` blocks + new `style.css` + `main.js` import + the CI guard.
- Do NOT delete untracked files / do NOT run `git clean` (pipeline/ + design.md are
  SSOT artifacts). Leave changes **unstaged** — the orchestrator commits + pushes.
- zh-TW only; any new user-facing text is Chinese, no simplified chars.
- Preserve exact hex values in the tokens (do not "improve"/shift colors) so the
  build renders identically and the 99 tests stay green.
- After the refactor, `grep -rhoE '#[0-9a-fA-F]{6}' frontend/src/**/*.vue` must print
  nothing. If any `#3a3560`-style value is needed in a component, it must be a
  `var(--token)` — that is the whole point.

## Variant / gate
- Variant B (single Coder) — pure-CSS refactor is not a hard multi-solution problem.
- Deterministic anchor = CI (this project has no verify.py). Orchestrator reproduces:
  `npx vitest run` (99 green) + `github_ci_gate.py <sha>` cross-checked vs
  `actions/runs?head_sha=…`. Coder self-report is a LEAD, not the verdict.
