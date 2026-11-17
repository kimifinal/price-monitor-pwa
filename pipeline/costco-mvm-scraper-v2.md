# costco_mvm_scraper — v2 重做設計

> **重做動機**：研究 3mi.ai/好市多雷達 競品後，發現其資料源是我們之前沒用的
> **`/rest/v2/taiwan/products/search` API**。該 API 直接回傳 8,458 筆完整
> 結構化商品 JSON（SKU/價格/原價/庫存/圖片/標籤），且純 curl 可抓（無需瀏覽器），
> 遠勝 v1 的 vision 抽圖方案。此設計取代 `costco_mvm_scraper.js` v1（vision 方案）。

## v1 vs v2 對照

| 項 | v1（vision 抽 MVM 圖） | v2（API 全量商品） |
|---|---|---|
| 資料源 | MVM 6 tab 的 CMS JSON + 圖片 | `/rest/v2/taiwan/products/search` API |
| 商品數 | 122 筆（僅 MVM 檔期特價） | 8,458 筆（全量目錄） |
| 價格 | vision OCR 抽圖（慢/貴/易錯） | JSON 直取 `price.intValue`（快/準/免 vision） |
| 庫存 | 無 | `stock.stockLevelStatus` |
| 賣場/線上 | 無（靠 vision 判 decal） | `warehouseFulfilled` + `decalData` |
| 圖片 | 需 vision 抽位元組 | `images[].url` 直鏈（JPG） |
| 抓取成本 | ~10s/張 vision call | ~0.5s/curl，全量 < 1 分鐘 |
| CI 可測 | 需 mock vision | 純 HTTP，易 mock |
| CRON 可跑 | 需瀏覽器 | 純 curl，免瀏覽器 |

## 關鍵 API（已 PoC 驗證 2026-11-16）

### 1. 商品搜尋（全量）
```
GET https://www.costco.com.tw/rest/v2/taiwan/products/search
    ?fields=FULL&query=<搜索词>&limit=20&sort=name|relevance&cat=<分類code>
Headers: User-Agent: <browser UA>, Accept: application/json, Referer: /search
→ HTTP 200，~0.5-0.9s，純 curl 可抓（無 cookie/CSRF）
```

**回傳結構**（已驗證）：
```json
{
  "products": [
    {
      "code": "2048748",                          // SKU
      "name": "Charmin 超柔捲筒衛生紙 197張 X 30卷",
      "englishName": "Charmin Ultra Soft Bath Tissue",
      "price": "{\"intValue\":999}",              // 售價 JSON string
      "basePrice": "{\"intValue\":999}",          // 原價（折扣判斷）
      "stock": "{\"stockLevelStatus\":\"inStock\"}",
      "warehouseFulfilled": false,                // 賣場出貨
      "productCartGroupAvailableInWarehouse": ...,
      "shippingIncluded": true,
      "decalData": [{"value":{"altText":"速配"}},{"value":{"altText":"Costco網路獨家商品"}}],
      "images": [{"url":"/medias/...jpg","format":"product"}],
      "url": "/Household-Baby-Toys/.../p/2048748"
    }
  ],
  "pagination": {"currentPage":0,"pageSize":20,"totalPages":423,"totalResults":8458},
  "facets": [
    {"name":"category","displayName":"商品分類","values":[
      {"code":"111005","name":"22K-24K 黃金擺件","count":1}, ... ]},  // 90+ 分類 code
    ...
  ]
}
```

**重點**：`price` / `basePrice` / `stock` / `decalData` / `images` 都是 JSON **string**，
需 `JSON.parse` 二次解。折扣 = `basePrice - price`。

### 2. 分頁 — **已解決 (2026-11-16)**

**關鍵發現：分頁參數是 `currentPage`，不是 `page`。** URL bar 的 `?text=1&page=1` 是 SPA 路由參數，
但實際 API 分頁用 `currentPage=N`。誤用 `page` 永遠回 page 0。

```
GET ...products/search?fields=FULL&query=1&pageSize=48&currentPage={N}&lang=zh_TW&curr=TWD
```

實證（query=1, pageSize=48）：
- `currentPage` 0→6 單調分頁，每頁 48 筆，334 = 7×48 零重疊 ✓
- 全 177 頁 ≈ 5 分鐘抓完 8,458 筆（每頁 ~1s，含 0.2s 延遲防 429）
- 折扣自動偵測：`price < basePrice` 即為特價，PoC 5 頁抓到 5 筆

**實作**：`data/costco_catalog/scrape_full.py` — 增量落檔、每 10 頁 save 一次、
retries=3 + 指數退避防 300s kernel timeout 丟失進度。

## 資料模型（SSOT）

落 `data/costco_catalog/`（替換 `data/costco_mvm/` 定位）：
```json
{
  "_meta": {"source":"costco-api","captured_at":"ISO","total":8458},
  "products": [
    {"sku":"2048748","name":"...","englishName":"...",
     "price":999,"basePrice":999,"discount":0,"discount_pct":0,
     "stock":"inStock","warehouse":false,"online_only":true,
     "decals":["速配","Costco網路獨家商品"],
     "category":"Household Essentials","image":"...jpg","url":"..."}
  ]
}
```
- 歷史 SSOT：`data/costco_catalog/history_data.json`（daily-diff 可跟蹤）
- Manifest：`data/costco_catalog/manifest.json`（抓取時間/來源/總數）

## 架 構 方 式

```
costco_mvm_scraper.ts（重做）
├── fetchCatalog()      → 遍歷全量商品（解分頁）→ products[]
├── detectChange()      → 對比上次 history_data.json
│   ├── price_drop      → price < basePrice 或 < 昨日
│   ├── out_of_stock    → stock 變 outOfStock
│   └── new_item        → 新增 SKU
├── alert()             → 降价/缺貨/新品 → 推送通知
└── fallback            → API 404 → 用歷史快照不 crash（離線測試）
```

## 待辦（v2 實作前）
- [ ] 解分頁機制（A/B/C 哪條通）→ 決定能否遍歷全 8,458 筆
- [ ] 驗證 `cat=` 分瀏覽 endpoint 回傳全分類商品
- [ ] 確認 API rate limit（連打 423 頁是否會被 throttle）

## 測試（離線）
- `catalogScraper.fallback`：API 404 → 用 fixture 快照，不 crash
- `detectChange`：price_drop / out_of_stock / new_item 三情境
- 禁 vision 依賴（全改 HTTP API）
- 上述「禁 vision」僅適用於 item 層；MVM 檔期內容仍須 vision，見下節。

---

## § 分工：API 可全自動 vs 只能半自動 (vision) — 2026-11-17 實測

> 狀態更新：上段「待辦（v2 實作前）」的解分頁 / 全量 8,458 已於 2026-11-16~17
> 解決——空 `query=` + `currentPage` 分頁 → 全量 **10,049** 筆，落
> `data/costco_catalog/products.full.json`。此節取代其定位。

### ✅ 可全自動（全量 API，免 vision）— item 層
`detectChange` 直接比 `decals` + `price`/`basePrice`/`stock` 的 daily diff 即可自動抓：
- **降價 / 特價**：`price < basePrice`，或 `decals` 新增「限時特價 / 優惠特價」
- **缺貨**：`stock.stockLevelStatus` → `outOfStock`
- **新品 / 標籤變**：新增 SKU，或 `decals` 新增「網路獨家 / 新品推薦」

`decals` 現值分布（全量 10,049 筆）：限時特價 170、優惠特價 66、網路獨家 4,693、新品推薦 386。

### ❌ 只能半自動 — MVM 檔期內容
「某個 MVM 檔期內有哪些商品 + 檔期日期」這層**公開 API 抓不到**（2026-11-17 實測）：
- `/rest/v2/taiwan/promotions?type=<mvm|mvm2|promotion|...>` 一律回 **`AccessDenied`**；連帶
  homepage cookie 也開不了 → 是 server 端 auth 閘，非少傳參數
- content 頁 `/content/fy27pX-mvm2-*` 是**純 SPA**：HTML 0 商品資料（0 CJK / 0 SKU / 0 price），
  curl 抓不到，須瀏覽器攔截其內部 XHR
- homepage 未列現行檔期 slug（頁內 `mvm-w1~7` 是舊 config 雜訊 `{"key":"/fy21p1-autumnmvm-w*","value":"/savings"}`，
  非現行 `/content/fy27*` 連結）→ 無可靠訊號「預測下一個新檔期」

⇒ 抓 MVM 檔期內容維持 v1 方案：**Playwright 截圖 + vision 抽價**（或瀏覽器攔 XHR）。

### 分工小結

| 需求 | 路徑 | 全自動? |
|---|---|---|
| 降價 / 特價 / 缺貨 / 新品（item 層） | 全量 API + `decals` diff | ✅ 全自動 |
| MVM 檔期內容（策展分組 + 檔期日期 + 該組商品） | 維持截圖 + vision | ❌ 半自動 |
| 偵測「有新 MVM 檔期出現」（活動層） | 無可靠公開 HTTP 訊號 | ❌ 半自動（靠 vision 比對） |
