# ISSUE #29 — feat(ui): mobile `touch-action: manipulation` on interactive controls

> Issue URL: https://github.com/kimifinal/price-monitor-pwa/issues/29
> 分支: `feature/touch-action` (base `master @ 516d4d3`)
> 架構師: Kimi (parent agent) | 日期: 2026-11-15
> 純 CSS + 一則 CSS-source guard test。不碰 `src/lib/`、不碰 #21 的 OKLCH token 值、不碰 #22 的 44px/`:focus-visible`/`prefers-reduced-motion`。

## 背景 / 問題

#22 已為互動控制加上 44×44px 觸控區，但 `src/style.css` 的互動 selector **沒有設 `touch-action`**。移動裝置上有兩個真實問題:

- **iOS Safari 雙擊 zoom**: 快速 tap 一個按鈕觸發 viewport `zoom`, 用戶想快速切換卻被放大畫面攔截。
- **`pan`/`scroll` 手勢衝突**: `touch-action:auto` 讓 tap 與 scroll 競奪, 造成「tap 卻捲動」的假綠(headless e2e 不會觸發, 實機會)。

## 目標

在 `src/style.css` 的互動 selector 加 `touch-action: manipulation` — 禁 double-tap-zoom, 保留 pan/scroll。`-webkit-touch-callout`/`user-select` 不在本 issue 範圍(留給 device-test 階段)。

## 實作事實(架構師已實測, 2026-11-15)

- **`touch-action` 放置點**: `src/style.css` 的 A1 塊現有互動 selector:
  - 規則 1: `button, [role='button'], a[href], input, textarea, select { min-height: 44px; box-sizing: border-box; }`
  - 規則 2: `button, [role='button'], a[href] { min-width: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }`
  - **新增一條專用規則** `button, [role='button'], a[href] { touch-action: manipulation; }` (獨立於 A1/A2, 易 grep-guard 命中, 不污染既有 min-height 規則)。
- **所有互動控制都是真 `<button>` 元素**: `加入追蹤`(AddItemForm)、`刪除`(ItemCard `.remove-btn`)、`we-export`/`we-import`/`we-reset`/`we-copy`(WatchlistEditor)。全局 `button { touch-action: manipulation }` 在 style.css(非 scoped)即覆蓋全部 — 4 個仍有 `<style>` 的 .vue 不需改。
- **代碼庫無 `.chip` class**: issue 文字「watchlist chip」指的就是上述按鈕。grep-guard **不要**尋找不存在的 `.chip`。

## 驗收準則 (AC)

| # | 驗收 | 判定方式 |
|---|---|---|
| AC1 | grep-guard: 互動 selector 必須命 `touch-action: manipulation` | 新增 `frontend/tests/unit/touch-action-css-source.test.js`, 照 #22 `a11y-css-source.test.js` 模式(`import.meta.url` + `node:` specifier, **禁 `process.cwd()`**), 斷言 `src/style.css` 含 `touch-action:\s*manipulation` 在 `button` / `[role='button']` 的規則上; CI 必綠 |
| AC2 | 無視 `@media (hover: hover)` — 觸控裝置直接生效 | grep 確認 `touch-action` **不在** `@media (hover: hover|pointer)` 區塊內 |
| AC3 | 不動 `src/lib/`、不碰 #21 token 值、不碰 #22 的 44px/`:focus-visible`/`prefers-reduced-motion` | `git diff master -- frontend/src/lib/` 空; `style.css` 無新增裸 hex; #22 的 a11y 守衛 test 仍綠 |
| AC4 | 現有 unit + blocking e2e(compare / watchlist)全綠 | `npx vitest run` + `npx playwright test e2e/compare.spec.js e2e/watchlist.spec.js` |
| AC5 | 手動驗: 快速 tap 按鈕不觸發 viewport zoom(選做) | `browser_exec` 或真機; `touch-action` 出現在 computed style |

## 範圍(嚴禁做)

- ❌ 不改 `src/lib/`(SSOT 守衛會 RED)
- ❌ 不新增/修改 OKLCH token 值(#21 範圍)
- ❌ 不碰 #22 的 44px min-height / `:focus-visible` 環 / `prefers-reduced-motion` / contrast
- ❌ 不新增 `-webkit-touch-callout` / `user-select`(不在本 issue 範圍)
- ❌ 不尋找不存在的 `.chip` selector
- ✅ 只改 `frontend/src/style.css`(加 1 條規則)+ 新增 1 則 CSS-source test
- ✅ 可選: 在 `design.md` 加一行註解說明 `touch-action` 的 placement(架構師可選, 不強制)

## 提交格式

- 2-3 小 commit on `feature/touch-action`:
  1. `feat(fa11y)[#29](style.css): add touch-action: manipulation to interactive controls`
  2. `test(fa11y)[#29](style.css): CSS-source guard for touch-action`
  3. `docs(fa11y)[#29]: note touch-action placement in design.md` (可選)
- 推 `feature/touch-action` 到 remote(不 merge master — 等 user 確認 CI 綠後 squash)。

## 注意

- 本 issue 是 #22 的 mobile 跟進; #22 的 44px 是「能不能點到」, `touch-action` 是「點到時不被手勢攔」。
- `touch-action: manipulation` 的權衡: 禁 double-tap-zoom 但保留 pan/scroll; 比 `touch-action: none`(也禁 pan)對比價 PWA 更友善。
- **ESLint 陷阱**: 守衛 test 用 `import.meta.url` + `node:` specifier(跟 #22 的 `a11y-css-source.test.js` 一樣), 避免 `process.cwd()` 的 `no-undef` 報錯。
