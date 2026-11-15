# ISSUE #24 — refactor(ui): 兩套 watchlist 語意分層（A方案：分層命名）

> Issue URL: https://github.com/kimifinal/price-monitor-pwa/issues/24
> 分支: `feature/watchlist-relabel` (base `master @ ecc251d`)
> 架構師: Kimi (parent agent) | 日期: 2026-11-15
> **決策：A 分層命名**（使用者 2026-11-15 確定）

## 背景 & 問題

同頁存在兩套「watchlist」語意，使用者混淆：
- `追蹤中（N）`：手動加入的 `items`（App.vue `AddItemForm` / `ItemCard`），現無 icon
- `🎯 個人化通知門檻（離線可編輯）` + `🎯 個人化追蹤（N）`：`WatchlistEditor` 的 6 預設 gate 種子，兩處都用 🎯

兩處同名 icon（🎯）造成混淆。

## 決策：A 分層命名

| 概念 | 現名 | 新名 | Icon | 所在 |
|---|---|---|---|---|
| 手動加入項 | `追蹤中（N）` | **🎯 手動追蹤（N）** | 🎯 | `App.vue` L106 |
| Gate 種子區 | `🎯 個人化通知門檻` + `🎯 個人化追蹤（N）` | **⚙ 自動門檻 Gate（...）** | ⚙ | `App.vue` L118 + `WatchlistEditor.vue` L147 |

**原理**：🎯 給使用者的「手動目標」（他追蹤的商品）；⚙ 給系統的「自動門檻」（預設種子 gate）。語意清晰，icon 不重覆。

## 實作事實（架構師已實測）

1. **e2e 安全**：`watchlist.spec.ts` 用 `加入追蹤(button)` / `測試徽章(heading)` / `刪除(button)`，不依賴被改的字串 → 重命名不會破 e2e。
2. **無 i18n**：字串直接在 `.vue` template（非 i18n 檔案），改 3 處即可。
3. **`App.vue` L107 副標題** `手動加入的名單，依緊迫度排序——目標價跌破現價就通知。` 已含「手動加入」→ 保留不動（它強化新 🎯 手動追蹤 語意）。
4. **後端不碰**：`git diff master -- backend/` 必須空。這是 pure UI 語彙重命名，不是邏輯重命名。後端內部 `watchlist (#4 gate)` 名稱保留（它是 logic SSOT 名，不是 user-facing label）。
5. **`WatchlistEditor.vue` L2 註解** `the #4 個人化 watchlist` → 更新為 `the 6 default seed gate (⚙ 自動門檻 Gate)`，避免日後混淆。

## 驗收準則 (AC)

| # | 驗收 | 判定 |
|---|---|---|
| **AC1** | `App.vue` 手動區 `🎯 手動追蹤` + `App.vue`/`WatchlistEditor.vue` gate 區 `⚙ 自動門檻 Gate` | 新增 `frontend/tests/unit/watchlist-relabel-css-source.test.js`（同 #29 / #22 的 source-guard 模式），斷言：(a) `App.vue` 含 `🎯 手動追蹤`；(b) `App.vue` 含 `⚙ 自動門檻 Gate`；(c) `WatchlistEditor.vue` 含 `⚙ 自動門檻 Gate`；(d) 兩處舊字串 `追蹤中`、`🎯 個人化` 皆不存在（防回歸）。用 `import.meta.url` + `node:fs` 解析，**不用 `process.cwd()`** |
| **AC2** | 無 icon 重覆 | grep-guard：同一檔案內不會同時出現 `🎯` 在兩個 h2 區；或新 test 斷言 `🎯` 字串只在 `App.vue` 的手動區出現 1 次（gate 區用 ⚙） |
| **AC3** | `git diff master -- frontend/src/lib/ backend/` 空 | 重命名僅改 UI label，不碰 `watchlist.js` 的 `DEFAULT_WATCHLIST` 種子邏輯、不碰 `monitor.js` 的 `shouldAlert` / `priceVerdict`、不碰 `backend/any` |
| **AC4** | 現有 107/107 前端測試全綠 + 新 test 加入 | `npx vitest run` 全綠 |
| **AC5** | CI 全綠 | GitHub Actions CI/CD 全綠 |
| **AC6** | 無裸 hex 新增、無 OKLCH token 值改動 | `git diff master -- frontend/src/style.css` 無新增 hex（此 issue 純 template 改動，不應碰 style.css） |

## 範圍（嚴禁做）

- ❌ 不碰 `frontend/src/lib/monitor.js` / `frontend/src/lib/watchlist.js`（SSOT 邏輯，grep-guard 會 RED）
- ❌ 不碰 `backend/` 任何檔案（SSOT 邏輯 + test 斷言）
- ❌ 不碰 `frontend/src/style.css`（不新增 hex、不新增 token）
- ❌ 不新增 `@media (hover)` 或改 #22 的 a11y 規則
- ✅ 只改 3 處字串：`App.vue` L106 (`追蹤中` → `🎯 手動追蹤`) + L118 (`🎯 個人化通知門檻（離線可編輯）` → `⚙ 自動門檻 Gate（離線可編輯）`)、`WatchlistEditor.vue` L147 (`🎯 個人化追蹤` → `⚙ 自動門檻 Gate`)、`WatchlistEditor.vue` L2 註解
- ✅ 新增 1 則 component-source guard test

## 提交格式

- 2-3 小 commit on `feature/watchlist-relabel`:
  1. `refactor(fa11y)[#24](App.vue,WatchlistEditor): layer watchlist naming — 🎯 手動追蹤 vs ⚙ 自動門檻 Gate`
  2. `test(fa11y)[#24]: component-source guard for watchlist relabel (prevents icon duplication regression)`
- 推 `feature/watchlist-relabel` 到 remote（不 merge master，等 CI 綠 + user 授權後 squash）。

## 注意

- 這是語彙重命名，不影響邏輯；但 test 必須斷言新 label 存在 + 舊 label 消失，防止未來回归。
- 舊 test `watchlist.test.js` 斷言 `DEFAULT_WATCHLIST` 邏輯不变 → 不應被本次重命名影響 → 全綠即證 SSOT 無破。
- e2e `watchlist.spec.ts` 不依賴重命名的字串 → 不會被破。
