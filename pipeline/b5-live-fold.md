# B5 — 即時比價摺疊/篩選（issue #23）

**系列 #21 · design §5.1（Tier 3）· 純前端，不動 `src/lib` 比價/判定邏輯，維持雙端 SSOT。**

## 背景（實測，非 issue 舊數）
- 即時比價 `liveCards`（`lib/history.js loadLiveHistory` → `mapItem`）**現 52 張卡**（issue 寫 47、已過時）。
- 卡結論**全部走 `lib/monitor.js priceVerdict`（SSOT，mirror `backend/models.py`）**：
  `all_time_low`（歷史最低）/ `good_deal`（≥15% off high，"較近低點 ▼X%"）/ `near_high`（≤5%）/ `stable` / `unknown`。
- 卡 shape：`{name, current, metrics{points, atAllTimeLow, dropPctFromHigh}, url, source, currency, tag, series?}`。
  → `priceVerdict(card.metrics)` 回 `{verdict, label, dropPct}`。
- live 段在 `App.vue` L160–176：當 `<price-history v-for="card in liveCards">` 全渲染 52 卡 + skeleton/empty。
- **e2e 守衛**：`tests/e2e/offline.spec.ts` 斷言 `section[data-section="live"]` 有 visible `.price-history[data-verdict]` + 一個 `path`(sparkline)。
  → **fold/filter 後 live 段絕不可 0 卡渲染**（須 fallback all）。

## 目標
1. **預設摺疊**：live 段**只渲染 top N 觸發卡**（DOM 大幅減），其餘摺在「展開其餘 M」按鈕後。
2. **篩選 toggle 三態**：`全部 / 僅觸發 / 僅近低點`。
3. **DOM 減**：folded 時只 mount 可見卡（`v-for` on 已 fold 的 array，非全 52）。
4. **覆誢**：`lib/live-fold.js` 全 unit + live 段 empty-fallback + fold toggle 有 test；既有 164 + e2e 全綠。

## 設計

### （A）新增純模組 `frontend/src/lib/live-fold.js`（unit-testable、零 DOM、複用 verdict SSOT）
```js
import { priceVerdict } from './monitor.js'
// 複用既有判定（不動 monitor.js）：
//   觸發 = 值得現在買：all_time_low ∪ good_deal(≥15% 降幅)
//   近低點 = good_deal（≥15% off high，verdict label 即「較近低點」）—— 觸發的子集
export function isTriggered(card) {
  const v = priceVerdict(card?.metrics)?.verdict
  return v === 'all_time_low' || v === 'good_deal'
}
export function isNearLow(card) {
  return priceVerdict(card?.metrics)?.verdict === 'good_deal'
}
const FILTERS = {
  all:        () => true,
  triggered:  (c) => isTriggered(c),
  'near-low': (c) => isNearLow(c),
}
export function filterLive(cards, filter = 'all') {
  const fn = FILTERS[filter] ?? FILTERS.all        // 未知 filter → all
  return (Array.isArray(cards) ? cards : []).filter(fn)
}
export const FOLD_LIMIT = 6                          // 預設摺疊每屏 visible 卡數
export function foldCards(cards, { expanded = false, limit = FOLD_LIMIT } = {}) {
  const arr = Array.isArray(cards) ? cards : []
  if (expanded || arr.length <= limit) return { visible: arr, foldedCount: 0, total: arr.length }
  return { visible: arr.slice(0, limit), foldedCount: arr.length - limit, total: arr.length }
}
```
**約束**：
- 只 import `priceVerdict`；**禁改 `monitor.js`/`history.js`/`models.py`**（判定邏輯 SSOT 不動）。
- 未知 filter → all（防禦）。
- `isTriggered` ⊃ `isNearLow`（near-low 是 triggered 子集；design note 寫清楚，UI label 用「近低點」避免與「觸發」撞義）。

### （B）App.vue live 段改造（L160–176 區段 + script 頂端 import）
- 新增 reactive：`const activeFilter = ref('triggered')`（預設僅觸發＝issue「只顯示觸發的 N 條」）、`const expanded = ref(false)`。
- 導入 `import { filterLive, foldCards, FOLD_LIMIT } from './lib/live-fold.js'`。
- 計算：
  ```js
  const filtered = computed(() => filterLive(liveCards.value, activeFilter.value))
  // empty-fallback：filter 命中 0 卡時仍 fallback all，保住 e2e「live 段要有一張卡」+ 不讓區塊消失
  const shownSource = computed(() => (filtered.value.length ? filtered.value : liveCards.value))
  const fold = computed(() => foldCards(shownSource.value, { expanded: expanded.value }))
  ```
- 模板 live 段替換為：
  ```html
  <template v-if="liveCards.length">
    <!-- 篩選 toggle：全部 / 僅觸發 / 近低點（radiogroup，:focus-visible，4px grid，token 色） -->
    <div class="live-filter" role="group" aria-label="即時比價 篩選">
      <button v-for="opt in FILTER_OPTS" :key="opt.k" class="live-chip"
              :aria-pressed="activeFilter === opt.k" :data-active="activeFilter === opt.k"
              @click="activeFilter = opt.k">{{ opt.label }}</button>
    </div>
    <!-- fold：只 render fold.visible；摺了才出「展開其餘」按鈕 -->
    <price-history v-for="(card, i) in fold.visible" :key="`live-${i}`" :card="card" />
    <button v-if="fold.foldedCount > 0" class="live-fold" @click="expanded = !expanded"
            aria-expanded="false" data-section="live-fold-toggle">
      {{ expanded ? '收起其餘' : `展開其餘 ${fold.foldedCount}` }}
      <section-icon :name="expanded ? 'chevron-up' : 'chevron-down'" title="展開/收起" />
    </button>
    <p v-if="!filtered.length" class="subtitle">此條件 0 筆，顯示全部 {{ liveCards.length }} 筆</p>
  </template>
  <skeleton-cards v-else-if="loading" :count="3" />
  <p v-else class="subtitle">尚無即時資料</p>
  ```
  - `FILTER_OPTS = [{k:'all',label:'全部'},{k:'triggered',label:'僅觸發'},{k:'near-low',label:'近低點'}]`。
  - `SectionIcon` 加 `chevron-up`/`chevron-down`（line-icon、currentColor，**禁 emoji**，sloplint 30a）。
  - 摺疊/展開用 `expanded`；摺時 `fold.visible` 只有 ≤6 卡 mount（DOM 減）。

### （C）anti-slop 守衛（全部強制）
- **emoji 禁止**：展開/收起用 `SectionIcon` chevron，非 ▲▼⤡。
- **4px grid**：live-filter/live-fold padding/gap 全 4 的倍數。
- **`:focus-visible`**：chip + fold button 有 `:focus-visible` outline（accessibility）。
- **`:disabled`**：filter 全命中空時 chip 不禁用（可切回 all）；fold button 僅 `foldedCount>0` 才渲染。
- **token 色**：全部 `var(--*)`（`--good-deal/--success/--warn/--link/--text-3`），無 hardcoded hex。
- **body-face badge**：無。
- `gate_sloplint.mjs` 0 enforceable blocking（gate 20/48 deferred excluded）。

### （D）覆誢（unit + e2e）
- `tests/unit/live-fold.test.js`（新）：filterLive 三態、foldCards（expanded/未 expanded/<=limit/空）、isTriggered/isNearLow 邊界（at_all_time_low、15% 邊界、near_high 不算）、unknown-filter→all、非陣列→[]。
- `App.vue` empty-fallback 行為：unit 或 e2e 驗「filter 0 卡時 live 段仍渲染卡」。
- **既有 164 unit + 3 e2e（compare/offline/watchlist）全綠**；`offline.spec.ts` 對 `[data-section="live"]` 的卡/render 斷言須過（empty-fallback 保底）。
- 全綠：`npm run test:unit`、`lint`、`node scripts/gate_sloplint.mjs`、`build`、`playwright test`（e2e）。

## 驗收
- live 段 default 只 mount ≤6 卡（foldedCount = total−6，52 卡情境 → foldedCount=46）。
- 三態篩選 + 摺疊 toggle 互動正常 + 有 test。
- 前端 5 gate 全綠 + CI 綠（PR）。
- 純前端、`monitor.js/history.js/models.py` byte-unchanged。
