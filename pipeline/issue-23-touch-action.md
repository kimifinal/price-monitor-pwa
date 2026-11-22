## 背景 / 問題

#22 已為 `price-monitor-pwa` 加上 44×44px 觸控區，但互動控制（watchlist chip、Import/Export 按鈕、ad-filter toggle）目前 **沒有設 `touch-action`**。移動裝置上會有兩個真實問題：

- **iOS Safari 雙擊 zoom**：快速 tap 一個 chip 觸發 viewport `zoom`（`double-tap`），用戶想快速切換 watchlist 卻被放大畫面攔截。
- **`pan`/`scroll` 手勢衝突**：某些 touch 容器上，`touch-action:auto` 讓 tap 與 scroll 競奪，造成「tap 卻捲動」的假綠（headless e2e 不會觸發，實機會）。

## 目標

在互動 selector（`button`、`.chip`、import/export 按鈕）加 `touch-action: manipulation` —— 禁 double-tap-zoom、保留 pan/scroll。若有長按複製型目標，再補 `-webkit-touch-callout: none; user-select: none;`（但那是 device-tap-callout，本 issue 暫不含，留給 #22 的 device test 範圍處理）。

## 驗收準則 (AC)

| # | 驗收 | 判定方式 |
|---|---|---|
| AC1 | CI grep-guard：互動 selector 必須帶 `touch-action: manipulation` | 新增 grep-guard：`.vue` 的 `.btn` / `.chip` / `button` 等互動 selector 必須命中 `touch-action:\s*manipulation`；不命中 CI RED |
| AC2 | 無視 `@media (hover: hover)` —— 觸控裝置直接生效 | `style.css` 不在 `@media (hover:pointer)` 內包 `touch-action` |
| AC3 | 不動 `src/lib`、不碰 #21 的 token 值、不碰 #22 的 44px/`:focus-visible`/`prefers-reduced-motion` | `git diff master -- src/lib/` 空；grep `.vue` 0 裸 hex |
| AC4 | 現有 unit + blocking e2e（compare / watchlist）全綠 | `npx vitest run` + `npx playwright test e2e/compare.spec.js e2e/watchlist.spec.js` 通過 |
| AC5 | 手動驗（手機或模擬）：快速 tap `.chip` 不觸發 viewport zoom | `browser_exec` 或在真機確認；`touch-action` 在 computed style 上存在 |

## 範圍

- 純 CSS：`style.css` 加入互動 selector 的 `touch-action: manipulation`（可放 `:root` 後的全局 selector 或各元件的 `button,.chip` 規則）。
- 新增一則 `touch-action` unit/CSS-source 守衛 test（同 #22 的 `a11y-css-source.test.js` 模式，避免 `process.cwd()` 陷阱、用 `import.meta.url` + `node:` specifier）。
- 不碰 `src/lib/`、不改 #21 的 OKLCH token 值、不改 #22 的內容、不碰 `design.md` 的 `--md-*` 表。

## 注意

- 本 issue 是 #22 的 mobile 跟進；#22 的 44px 觸控目標是「能不能点到」，`touch-action` 是「点到的時候不被手勢攔」。
- `touch-action: manipulation` 的權衡：禁 double-tap-zoom 但保留 pan/scroll；比 `touch-action: none`（也禁 pan）對比價 PWA 更友善（用戶可能要在 list 上滑動）。
