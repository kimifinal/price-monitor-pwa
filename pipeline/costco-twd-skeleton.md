# ISSUE #25 — chore(ui): TWD 幣制去 .00 + 載入態 skeleton card

> Issue URL: https://github.com/kimifinal/price-monitor-pwa/issues/25
> 分支: `feature/costco-twd-skeleton` (base `master @ 806aae9`)
> 架構師: Kimi (parent agent) | 日期: 2026-11-15
> 系列 #21 · design.md §3 / §5.3

## 背景 & 問題

### A. TWD 去小數
台幣 (TWD) 無小數，但 `ItemCard.vue:29-30` 用 `item.price?.toFixed(2) || '0.00'` 顯示 `$1069.00`。
目前 0 筆手動項故未爆，但**邏輯已埋雷**：加一個手動項就出 `$xxx.00`。
另 `monitor.js` 的 `alertMessage` L64 也用 `$${item.target.toFixed(2)}` — alert 文字也有 `.00`。

**改法**：新增 `frontend/src/lib/format.js`（TWD 格式 SSOT）。
```js
// format.js — the ONE TWD money formatter (SSOT). TWD has no minor unit.
// Display = locale thousands separator, zero decimal (design.md §3).
export function formatTWD(n) {
  const v = Number(n || 0)
  return v.toLocaleString('zh-TW')   // 1069 -> "1,069"; no .00
}
// Prefix for display sites (keep the $ / TWD marker; drop the decimals):
export function moneyTWD(n) { return 'TWD ' + formatTWD(n) }   // -> "TWD 1,069"
```
- `ItemCard.vue:29-30`：`${{ item.price ... toFixed(2) }}` → `{{ moneyTWD(item.price) }}`、`{{ moneyTWD(item.target) }}`
- `PriceHistory.vue:65`：`Number(card.current || 0).toLocaleString()` → `{{ moneyTWD(card.current) }}`（加上 TWD 前綴，與 ItemCard 一致；原本已無小數，只補前綴 + 走 SSOT）
- `monitor.js alertMessage` L64：`\`$${item.target.toFixed(2)}\`` → `\`${moneyTWD(item.target)}\``（import format.js）

**SSOT 守衛的精修（重要）**：#25 允許 `lib/` 有**增量改動**，但**純決策函数不能動**：
- ✅ 允許：新增 `lib/format.js`；`monitor.js` 的 `alertMessage`（呈現層）改用 `formatTWD`
- ❌ 禁止改動（SSOT 決策邏輯，必須 byte-unchanged）：`shouldAlert` / `priceVerdict` / `sparkPath` / `findEntry` / `thresholdMet` / `percentBelowTarget` / `alertedItems` / `sortByUrgency` 的**函數體**
- 守衛方式：現有的 `monitor.test.js` + `watchlist.test.js` **必須全綠**（它們直接測這些決策函数 = 隱式 SSOT 守衛）；再加一則 grep-guard：`frontend/` 內無 `toFixed(2)` 用於價格（`.toFixed(1)` 在 SVG sparkPath 座標保留，不算價格顯示）。

### B. 載入 skeleton card
`App.vue:145`：`<p v-if="!liveCards.length" class="subtitle">正在載入離線快照…</p>` — 純文字，
- **layout shift**：文字高度 ≠ 真實 price-history card，載入完瞬間版面跳。
- **語意混淆**：empty 同時代表「還在載入」與「真的沒資料」。

**改法**：
1. `App.vue`：加 `const loading = ref(true)`，`onMounted` 的 try/catch 加 `finally { loading.value = false }`。
   載入區範本：
   ```html
   <template v-if="liveCards.length">
     <price-history v-for="(card, i) in liveCards" :key="`live-${i}`" :card="card" />
   </template>
   <skeleton-cards v-else-if="loading" :count="3" />
   <p v-else class="subtitle">尚無即時資料</p>
   ```
2. 新增 `frontend/src/components/SkeletonCard.vue`：mimic `PriceHistory.vue` 的結構高度（head 列 + spark 佔位 + foot 列），
   用 shimmer 動畫。`:count` prop 渲染 N 個佔位 card。
3. `style.css`：加 `.skeleton` / `.skeleton-card` 樣式 + `@keyframes skeleton-shimmer`。
   - 色用現有 token（`--surface` / `--border` / `--muted`），**不新增 token**（#26 才做 token 層）。
   - shimmer 走 `animation: skeleton-shimmer 1.5s infinite`；**遵從 #22 的 `prefers-reduced-motion`**：
     已有的 `@media (prefers-reduced-motion: reduce) { * { animation-duration: 0.001ms !important } }` 已覆蓋（grep-guard 會確認 skeleton 不繞過它）。
   - skeleton card 的 `min-height` 對齊 `PriceHistory` 卡片高度，避免 layout shift。

## 驗收準則 (AC)

| # | 驗收 | 判定 |
|---|---|---|
| **AC1** | 所有價格顯示無小數位 | `npx vitest run` 新 `format.test.js`：`formatTWD(1069)==='1,069'`、`formatTWD(0)==='0'`、`formatTWD(null/undefined/NaN)==='0'`、`moneyTWD(1069)==='TWD 1,069'`；grep-guard：`frontend/` 內 `toFixed(2)` 出现 0 次（`.toFixed(1)` 在 SVG 不受影響），用 source-guard test 斷言 |
| **AC2** | `alertMessage` 無小數 | 新 `monitor` test 或擴 `alertMessage` 測試：`alertMessage({name:'X',target:1069,price:500})` 字串不含 `.00` / 小數（含 `TWD 1,069`） |
| **AC3** | 決策 SSOT 未動 | `monitor.test.js` + `watchlist.test.js` 全綠（它們測 shouldAlert/priceVerdict/findEntry/thresholdMet — 隱式守衛決策邏輯 byte-unchanged）；grep 確認 decision 函數 signature 不變 |
| **AC4** | skeleton card 避免 layout shift | 新增 `SkeletonCard.vue` + `style.css` skeleton 樣式；新 source-guard test 斷言 `style.css` 有 `@keyframes skeleton-shimmer` + skeleton 樣式走 token（不裸 hex）+ `prefers-reduced-motion` 仍覆蓋 animation（`git diff` 確認 #22 的 reduced-motion 區塊未刪） |
| **AC5** | `loading` 語意正確 | `App.vue` 有 `loading` ref + try/catch/finally；skeleton 只在 `loading && !liveCards.length` 顯示；`liveCards.length` 顯示真實 card；否則 `尚無即時資料` |
| **AC6** | CI 全綠 + e2e 全綠 | `npx playwright test` compare + watchlist 全綠（PriceHistory e2e 的 price 顯示改 TWD 前綴，e2e 若 assert 舊格式要同步；但 e2e 只 assert 卡片存在/排序，不断言金額數字 → 應不影響，Coder 確認） |

## 範圍（嚴禁做）

- ❌ 不改 `shouldAlert` / `priceVerdict` / `sparkPath` / `findEntry` / `thresholdMet` / `percentBelowTarget` / `alertedItems` / `sortByUrgency` 的函數體（SSOT 決策邏輯）
- ❌ 不新增/改 OKLCH token 值（#26 範圍）— skeleton 用現有 token
- ❌ 不碰 `backend/`（雙端 SSOT）
- ❌ 不刪 #22 的 `:focus-visible` / `prefers-reduced-motion` / 44px 規則
- ✅ 改：`lib/format.js`（新）、`ItemCard.vue`、`PriceHistory.vue`、`monitor.js`（alertMessage import + 改用）、`App.vue`（loading + skeleton markup）、`components/SkeletonCard.vue`（新）、`style.css`（skeleton 樣式 + keyframe）、3 個新測試檔
- ✅ 可選：`design.md` 加 §5.3 skeleton 落地記錄

## 提交格式

- 3-4 小 commit on `feature/costco-twd-skeleton`：
  1. `feat(lib)[#25]: add TWD money-format SSOT (format.js) + apply in ItemCard/PriceHistory/alertMessage`
  2. `feat(ui)[#25]: loading skeleton card for live section (no layout shift, honors reduced-motion)`
  3. `test(ui)[#25]: format + skeleton source-guard tests`
- 推 `feature/costco-twd-skeleton` 到 remote（不 merge master）。

## 注意

- `design.md` 的「99 測試」已過時（現 112+）；AC 用「現有全綠 + 新增全綠」代替硬編 99。
- `format.js` 是新的展示層 SSOT，不影響 monitor.js 的純決策函数。
- 若 `toLocaleString('zh-TW')` 在 Node/jsdom test 環境行為差異，測試要 pin 預期字串（`1,069`）而非靠 locale engine；Coder 要確認 CI 的環境 locale。
- e2e compare.spec.ts 的 sparkline「依降幅排序」不斷言金額數字 → 改 TWD 前綴不影響；Coder 跑 e2e 確認。
