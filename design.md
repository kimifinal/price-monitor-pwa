# Design Spec — Price Monitor PWA

> 狀態：**提案（待你過目）**，未實作。通過後走四角色 pipeline，Coder 依此改。
> 目標：在**不破壞現有視覺**的前提下，建立設計 token 系統（CSS 的 SSOT），
> 補上 mobile a11y 硬傷，並處理效能/語意問題。改動可分階段合併（Phase 1 零視覺風險，先上）。

---

## 1. Chosen Aesthetic — Technical Mono · Dark Data Console

選定 **Technical Mono**（developer/data look 的變體），理由：

- 產品本質是「價格監控 console」——密集資料 + 狀態色（歷史最低 / 接近高點 / 觸發），
  最貼合 mono/serif-free、低雜訊、高資訊密度的風格。
- **保留既有紫色品牌調**（`#4a3f7a` accent，保留品牌色、移除 mascot 元素），不推翻視覺，只系統化。
- 低對比雜訊、克制的動效 —— 資料閱讀優先。

**Design principles（本 spec 要滿足的三條）**
1. **Token 優先**：任何色/間距/字級都引用 `:root` 變數，禁止元件內硬編 hex。
2. **可及性是預設**：觸控目標 ≥ 44px、焦點可見、`prefers-reduced-motion` 有守衛。
3. **一屏可讀**：資訊密集但一屏能抓到重點；47 卡這種要摺疊/篩選，不讓使用者滑 8000px。

---

## 2. Color Tokens（OKLCH · 語意化）

### 2.1 現狀問題（SSOT 違反）
- 實測：`:root` custom property = **0 個**；26 個 hex 值散落在 5 個 `.vue`，
  同語意色重複（成功綠有 `#4caf50` 與 `#8bc34a` 兩個、accent 紫在 5 處硬編）。
- 改一個色要改 5 檔 → 無法做主題化、無法保證一致。

### 2.2 目標 token（已驗證 OKLCH，與現有 hex 感知 1:1，零視覺風險）
> OKLCH 數值經 `sRGB→OKLab` 正解換算並過 validation（white L=1/C=0、green H≈142、blue H≈264）。
> 括號內為**現行 hex**，證明改動是「換語彙、不改顏色」。

```css
:root {
  /* 中性（略帶紫，維持品牌調） */
  --bg:        oklch(0.16 0.013 300.2); /* #0f0d13 */
  --surface:   oklch(0.19 0.012 300.4); /* #141218 */
  --surface-1: oklch(0.23 0.046 287.9); /* #1b1830 */
  --surface-2: oklch(0.17 0.023 292.1); /* #0f0d18 */
  --border:    oklch(0.29 0.045 288.7); /* #2a2740 */
  --border-2:  oklch(0.36 0.073 287.4); /* #3a3560 */

  /* 文字 */
  --text:      oklch(0.95 0.029 296.8); /* #efeaff  主 */
  --text-2:    oklch(0.75 0.046 296.7); /* #b0a8c8  次要 */
  --text-3:    oklch(0.64 0.051 290.3); /* #8a86a8  輔助 */
  --muted:     oklch(0.45 0.000 0);     /* #555555  停用/無資料 */

  /* 品牌 accent（紫） */
  --accent:        oklch(0.41 0.097 290.0); /* #4a3f7a */
  --accent-hover:  oklch(0.47 0.11  290.0); /* 亮一檔，取代 #3a3560 的 hover */
  --accent-soft:   oklch(0.30 0.05  290.0); /* #3a3560 邊框用 */

  /* 狀態色 */
  --success:     oklch(0.67 0.162 144.2); /* #4caf50 歷史最低/成功 */
  --success-tx:  oklch(0.84 0.108 158.5); /* #8ae0b0 成功文字 */
  --good-deal:   oklch(0.75 0.163 130.5); /* #8bc34a 接近低點 */
  --warn:        oklch(0.76 0.139 73.3);  /* #e6a23c 接近高點 */
  --danger:      oklch(0.69 0.127 20.8);  /* #e07a7a 移除/危險 */
  --danger-b:    oklch(0.35 0.044 334.4); /* #4a3345 危險邊框 */
  --sku:         oklch(0.83 0.169 90.5);  /* #f0c000 SKU 強調 */
  --link:        oklch(0.77 0.115 263.8); /* #8fb4ff 連結 */
}
```

### 2.3 落地方式（Phase 1，建議先上）
- 新增 `src/style.css`：`@layer tokens, base, components, utilities;` +
  `:root { ... }` 放上述 token；`main.js` 引入。
- 各元件把 hard-coded hex 全換成 `var(--…)`；**視覺零變化**（值已 1:1 對齐）。
- CI 加一個 grep guard：`src/**/*\.{vue,css}` 內 **禁止出現裸 hex**
  （`#xxxxxx`），守住 SSOT。（可選，與 `secrets-guard` 同思路。）

> **為何 OKLCH 而非 RGB**：OKLCH 感知均勻，調明度不偏色；未來加淺色主題只需覆寫 `:root` 一處。

---

## 3. Typography

### 3.1 現狀 bug
- `body` 字型 fallback 到 **`Times New Roman`**（serif）—— `font-family` 只設在 `.app`，
  根文件/輸入框基底是襯線體，與 UI 無襯線風格裂開。

### 3.2 改動
```css
@layer base {
  :root {
    --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", monospace; /* 價格/SKU 用 */
    --font-base: var(--font-sans);
  }
  html { font-family: var(--font-base); -webkit-font-smoothing: antialiased; }
  body { margin: 0; background: var(--bg); color: var(--text); }
}
```
- **字型 scale（fluid，`clamp()`）**：
  ```
  --fs-h1: clamp(1.5rem, 4vw, 2rem)     /* 現在 32px 固定，改 fluid */
  --fs-h2: clamp(1.15rem, 3vw, 1.35rem)
  --fs-body: 1rem
  --fs-sm: 0.85rem
  --fs-cap: 0.72rem                     /* caption/label */
  --fs-num: var(--fs-body)              /* 價格數字，等寬 font-variant-numeric: tabular-nums */
  ```
- 價格/SKU 用 **tabular-nums + 等寬**，避免數字跳動、對齊整齊。
- TWD 顯示：取消 `.toFixed(2)` 的 `$.00`（台幣無小數）→ `Number(...).toLocaleString('zh-TW')`。
  目前 0 筆手動項所以未爆，但 ItemCard 邏輯已埋此雷，一併清。

---

## 4. Layout

### 4.1 間距 scale（取代亂散 px）
```
--sp-1: 4px   --sp-2: 8px   --sp-3: 12px   --sp-4: 16px
--sp-5: 24px  --sp-6: 32px  --sp-8: 48px
```

### 4.2 圓角統一（現在 6/8/10/12 四種）
```
--radius-sm: 8px   --radius: 12px   --radius-lg: 16px   --radius-pill: 999px
```
卡片 = `--radius`，button = `--radius-sm`，tag = `pill`。

### 4.3 最大寬 + 兩欄
```
--max-w: 880px;
@media(min-width: 720px) {
  .app-main { display: grid; grid-template-columns: 1fr minmax(320px, 380px); gap: var(--sp-5); }
}
```

---

## 5. 效能 & 語意（Tier 3）

### 5.1 47 張比價卡 → 摺疊/篩選
- 實測：即時比價列 **47 張卡**、頁面 **8326px**。無分頁/篩選/摺疊。
- 改：即時比價預設**摺疊**（顯示觸發的 N 條 + 「展開其餘 42」），
  加一個篩選 toggle（全部 / 僅觸發 / 僅接近低點）。
- 或先做**分頁/`limit` 預覽**，長期上 virtual list。

### 5.2 兩套「watchlist」概念混淆
- 現在同一頁有 **`追蹤中（0）`**（手動加入的 `items` → ItemCard）與
  **`個人化追蹤（6）`**（`WatchlistEditor` 的 gate，同用 🎯 icon）。
- 建議：明確分層命名 ——
  - 「🎯 手動追蹤」→ 使用者自加，走 `items`（現 AddItemForm/ItemCard）
  - 「⚙ 自動門檻 Gate」→ 預設 6 種子，走 WatchlistEditor
- 或**合併語意**（一個 watchlist，gate 只是其中一個欄位）。需你定方向。

### 5.3 載入態 skeleton
- 「正在載入離線快照…」純文字 → 一個輕量 skeleton card（避免 layout shift、有回饋）。

---

## 6. 可及性 / a11y（Tier 2，mobile PWA 優先補）

| 專案 | 現狀 | 目標 |
|---|---|---|
| 觸控目標 | **11/11 按鈕 < 44px**（匯出/匯入 29px 高） | `min-height:44px` + `min-width:44px`（padding 撐大，視覺可保持小） |
| 焦點 | 無 `:focus-visible` | `outline: 2px solid var(--accent-hover)` 可見 |
| `prefers-reduced-motion` | 無 | 所有 transition 包在 `@media (prefers-reduced-motion: no-preference)` |
| 淺色主題 | 無（硬編 dark） | 可選 Phase 2：`@media (prefers-color-scheme: light)` 覆寫 `:root` |
| 對比 | 未測 | 用 token 後統一校 WCAG AA（`--text-3` 在 `--bg` 上需 ≥ 4.5:1） |
| 語意 | 部分 `div` 當 button | 真 `<button>`、語意 tag、`aria-label` 給圖示鍵 |

---

## 7. 改動清單（Before → After，依 phase）

### Phase 1 — Token 系統（**零視覺風險，建議先上**）
- 新增 `src/style.css`（`@layer tokens/base` + `:root` OKLCH token + type/spacing/radius scale）
- 5 個元件：所有 hard-coded hex/px/radius → `var(--…)`（值 1:1，視覺不變）
- `main.js` 引入 `style.css`；`body` 字型修正（修掉 Times fallback）
- CI grep guard：禁止 `src/**` 出現裸 hex（守 SSOT）
- 驗收：現有 99 前端測試全綠 + 視覺截圖 diff ≈ 0

### Phase 2 — a11y + 觸控（建議跟 Phase 1 一併或緊接）
- 44px 觸控目標、`:focus-visible`、`prefers-reduced-motion` 守衛
- 真 `<button>` 替代 `div[role]`、圖示鍵 `aria-label`

### Phase 3 — 效能 & 語意
- 47 卡摺疊/篩選、兩套 watchlist 分層（**需你定方向**）、載入 skeleton、TWD 去 `.00`

---

## 8. 驗收標準
- 前端 99 測試全綠（加 token 抽換不回退）；CI 全綠
- CI grep guard 通過（無裸 hex 殘留）
- 視覺截圖：Phase 1 後截圖與現狀 diff ≈ 0（證明「換語彙非改色」）
- Lighthouse a11y 分數 ≥ 90（Phase 2 後）
- 手機實測：觸控目標 ≥ 44px、焦點可見、無 layout shift

---

*產出者：Architect（frontend-aesthetic-engine）｜狀態：待 Kimi 過目後，走四角色 pipeline 實作。*
