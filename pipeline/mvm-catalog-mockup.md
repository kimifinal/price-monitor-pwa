# MVM 檔期目錄頁 — B4 設計 mockup + 規格

**狀態**：設計階段產物（mockup + 規格）。尚未建 `MvmCatalog.vue`（Coder 階段依本檔建）。
**產物**：
- 可離線開啟的 standalone mockup：`~/.hermes/cache/scratch/bshots/mvm-catalog-standalone.html`
- 全頁截圖：`~/.hermes/cache/scratch/bshots/mvm-catalog.png`
- 資料來源：`data/costco_mvm/2026-11-16_mvm_p4.json`（6 檔期，585 品項；離線 baked）

## 1. 為什麼要這個頁面

多變價（MVM）資料（`costco_mvm/*.json`）是 Costco 的**檔期促銷**目錄：一檔期（如「優惠期間 2026/10/26–11/22」）包含所有該期間的品項，每品項帶 `orig / promo / discount`（原價 → 促價 → 折幅）+ `price_type` + `category`。
現有 PWA 有即時比價（`items`），但**沒有離線可看的 MVM 檔期目錄**——這頁補上：選一個檔期，看該期間所有品項，離線可看。

## 2. 資料形狀（SSOT = `costco_mvm/*.json`）

```json
{
  "source": "Costco",
  "tabs": [
    {
      "tab_id": "fy27p3-mvm2-w1",
      "label": "優惠期間",
      "period": "2026/10/26 - 11/22",
      "n_products": 62,
      "description": "只限線上買 賣場沒有…（檔期說明文案）",
      "price_type": "online_only",
      "products": [
        { "sku": "153085", "name": "CONAIR 美康雅 二合一手持掛燙熨斗 GS3087W",
          "category": "家電", "price_type": "online_only",
          "orig": 620, "promo": 379, "discount": 241, "period": "W1" },
        ...
      ]
    },
    ... // 共 6 個檔期
  ],
  "price_types": {
    "online_only":       { "label": "線上專屬價格", "badge": "橙色小車", "meaning": "只在線上買 賣場沒有 沒有 比價 更優惠" },
    "store_online_diff": { "label": "賣場售價+線上優惠", "meaning": "這個價格 是現有的 線上 有更低 的價格" },
    "store_only":        { "label": "賣場價格", "meaning": "只有 賣場 有 沒有 線上" }
  }
}
```

**關鍵**：MVM 品項**沒有圖片欄**（僅 `sku/name/category/price_type/orig/promo/discount/period`）。→ image slot 目前為**佔位**（見 §4），等抓到圖片再補。

## 3. 設計 tokens（mirror `frontend/src/style.css`，hex 版＝現 live）

| token | 值 | 用途 |
|---|---|---|
| `--bg` `#0f0d13` | 背景 | 頁面深黑紫 |
| `--surface` `#141218` | 卡片底 | 品項卡、tab |
| `--surface-1` `#1b1830` | 次層 | image slot、cat tag 底 |
| `--surface-2` `#0f0d18` | 圖例背 | legend row |
| `--border`/`--border-2` | `#2a2740` / `#3a3560` | 卡片/邊框 |
| `--text`/`--text-2`/`--text-3` | `#efeaff` / `#b0a8c8` / `#8a86a8` | 主/次/微弱文字 |
| `--accent`/`--accent-hover` | `#4a3f7a` / `#6f5fc7` | active tab 邊框、focus ring、icon |
| `--success`/`--good-deal` | `#4caf50` / `#8bc34a` | 高折幅、省 $X |
| `--link` `#8fb4ff` | 藍 | 「查看」連結、線上專屬 badge |
| `--sku` `#f0c000` | 金 | image slot 的 SKU |
| `--font-mono` | — | 數字（SKU/價格/折幅/期間） |

折幅 badge 按 % 分級：≥25% `--success`、15–25% `--good-deal`、<15% `--text-2`。
類型 badge 依 `price_type`：`online_only`→`--link`、`store_online_diff`→`--good-deal`、`store_only`→`--sku`。

## 4. 元件結構（Coder 依此建 `MvmCatalog.vue`）

```
MvmCatalog.vue
├─ props:
│    tabs: Tab[]          // costco_mvm.json.tabs（6）
│    priceTypes: object   // costco_mvm.json.price_types（3）
│    initialTab?: string  // 預設 active tab_id（或「最新檔期」）
│    sourceDate?: string  // 抓取的日期，footer 顯示
│
├─ 區段標題（SectionIcon.vue，monochrome line-icon，禁 emoji — 過 slope gate 30a）
│    <h1> <SectionIcon name="catalog"/> 好市多 MVM 檔期
│    <p class="sub"> 每週檔期，離線 baked。選一檔期…（一句，禁破折號/中點 spam）
│
├─ 檔期 tab bar
│    <button class="tab"> × 6
│       .tab-label   = tab.label
│       .tab-period  = tab.period（mono tabular-nums；空則留空，禁「—」— 過 gate 19）
│       .tab-count   = tab.n_products（mono tabular-nums；無資料顯示 N/A，禁「—」）
│    active tab: .tab.active（--accent 邊框 + --surface-1 背）
│    全 8 states: hover / active / focus-visible / disabled（gate 26a/26b）
│
├─ 類型圖例（legend row）
│    3 條：badge（類型 label）+ 該 type 的 meaning
│
└─ 品項 grid（<main class="grid">，mobile 1-列，≥720px 2-列）
     MvmProductCard × n（該 active tab 的 products）
     ├─ .mvm-img   88×88 佔位（MVM JSON 無圖，現為 SKU mono + 「圖片待補」）
     ├─ .mvm-top   <span.cat> category ｜ <span.discount %> %（色碼，mono tabular-nums）
     ├─ <h2 class="mvm-name"> name        （h1→h2 循序；gate F21）
     ├─ .mvm-prices  orig（刪除線灰）＋ promo（大字 mono-bold）＋ 省 $X（--good-deal）
     └─ .mvm-foot  <span.badge> price_type ｜ <a class="mvm-link">查看</a>（純動詞，禁黏合箭頭 — gate 63）
```

### 與 `ItemCard.vue` 的對照（SSOT 重用）
- 卡片骨架（surface/border/radius + image slot + 價格行 + link）**沿用 `ItemCard.vue` 的 pattern**；
- 差異：MVM 品項**多 `orig→promo` + 折幅 badge + 類型 badge**，即時比價只有一個現價。
- 建議 `MvmProductCard.vue` 或直接在 `MvmCatalog.vue` 內 inline（量小，6 檔期 × 12–62 品項）。
- 數字一律 `moneyTWD()`（去 .00，沿用 `App.vue` 既有）。

## 5. App.vue 整合（wire-in）

- `App.vue` 新增一個 view/tab「MVM 檔期」（與即時比價並列），`<MvmCatalog :tabs="mvmTabs" :priceTypes="mvmPriceTypes" />`。
- `mvmTabs` / `mvmPriceTypes` 從 `data/costco_mvm/` 讀（離線 baked，`import` 或 fetch 同目錄）；
  可走 `lib/` 一 loader（仿 `loadItems`），或 build 時 bake。
- 6 個檔期 = 6 `<button class="tab">`；active state 用 `ref(activeTab)`，預設「最新／W1」。
- 圖示一律 `SectionIcon.vue`（#40 既有），禁 emoji 入 h2（gate 30a）。

## 6. sloplint 審計結果（anti-slop gate，`frontend/scripts/sloplint.mjs`）

跑 `node sloplint.mjs . --scope component`（獨立目錄，CI 同款）：

- **blocking FAIL（gate 19/63/24b/26a/26b…）= 0** ✅
- 唯一剩 **gate 20（Hallmark stamp, floor）= 1**，但 CI 的 `gate_sloplint.mjs` `EXCLUDE = {'20','48'}`，**現有 app 也靠此 exclude 過**→ CI 角度 0 blocking。
- 過程中修掉（mockup 已內建）：
  - gate 19：副標題空檔期/空 count 不再用「—」（gate「copy 不可破折號」）→ 改「N/A」/留空。
  - gate 63：（a）副標題中點 spam「品名 · 促價 · …」→ 改「、」；（b）「查看→」黏合箭頭 → 改純「查看」。
  - gate 41：品項卡明確 `color: var(--text)`。
  - gate 64：`.badge` 改 body face（mono 只給數字/code）。
  - gate 24b：spacing 全對齊 4px 網格（`--sp-1`=4px）。
  - gate 26a/26b：補 `:focus-visible` ring + `:disabled` + `:active`（a11y，全 8 states）；`:focus-visible` 用 `--accent-hover`。

## 7. 開問題 / 待確認

| # | 問題 | 建議 |
|---|---|---|
| Q1 | **圖片**：MVM JSON 無 image 欄。image slot 現為「SKU + 圖片待補」佔位。是否 (a) 暫留佔位、(b) 補抓圖片、(c) 用 category 圖示替代？ | 建議 (a) 先佔位、(b) 排進 Tier C（成本：要再爬 Costco 圖片）|
| Q2 | **6 檔期同屏**：一次渲染 6 tab × 最多 62 品項＝全 585 卡。還是 lazy（只渲染 active tab）？ | 建議 lazy：active tab 才渲染，6 tab 全可點但 grid 依 active。|
| Q3 | **排序**：現 mockup 依折幅 % descending。要嗎？或 SKU / 類別排序 / 分頁？ | 建議 default 折幅 desc + 提供「類別 / 金額」排序 chip。|
| Q4 | **類別 filter**：mockup 沒放類別 filter chip。要嗎（62 品項跨 13 類，filter 有用）？ | 建議加（cheap，且提升可讀性）。|
| Q5 | **折幅色碼斷點**：≥25% / 15–25% / <15% 合理嗎？ | 確認斷點。|
| Q6 | **active tab 預設**：預設「W1／最新檔期」OK？ | 確認。|
| Q7 | **MVM vs 即時比價 是否合併**：MVM 的 `orig/promo/discount` 跟即時比價（現價/歷史）是否可共用 ItemCard？ | 建議 MVM 獨立 `MvmProductCard`（欄位不同），共 style token，不共用 component。|

## 8. 下一步（Coder 階段，待 Kimi 確認 §7 後）

1. 依 §4 建 `MvmCatalog.vue`（+ 可能 `MvmProductCard.vue`），style 引用 `style.css` token（不硬編 hex，過 gate）。
2. 把 §6 的 gate 修法**內建**（focus/disabled states、純動詞連結、4px 網格、body-face badge、無「—」）→ PR 時 auto-check 綠。
3. `App.vue` 加「MVM 檔期」tab（§5）。
4. 跑 `npm run`（unit/e2e/lint/sloplint/build），綠後 commit + PR + 等 `同意`。
5. 圖片（Q1）若採 (b)，開 Tier C 抓圖任務。
