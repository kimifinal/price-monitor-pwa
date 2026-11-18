# Tier A — Costco item 層 detectChange + decal alert + fallback（#35 的可完成部分）

> 父里程碑：#35（MVM vision-phase）。本案 = Tier A（全自動、離線可驗證）。
> Tier B（MVM 檔期內容，vision 半自動）不在本案，留 §暫緩。
> SSOT 來源：`pipeline/costco-mvm-scraper-v2.md § 分工` + `backend/{history,alerts,scrapers}.py`。

## 範圍（只做 item 層，全用 fixture、不觸 live Costco API）

### A1 — `detectChange` 三情境離線測試
對「上一 snapshot vs 新 snapshot」做 diff，發出三種警報，**離線**測（fixture JSON）：
- `price_drop`：某 SKU 新 `price` < 上一 `price`，或 `price < basePrice`（即特價）
- `out_of_stock`：`stock.stockLevelStatus` 由 inStock → outOfStock
- `new_item`：新 snapshot 出現上一 snapshot 沒有的 SKU
驗收：三情境各有離線 fixture 觸發、且未觸發時**靜默**（不誤報）。

### A2 — decal-based MVM item alert
用全量目錄的 `decals`（限時特價 / 優惠特價 / 網路獨家 / 新品推薦）+ `price`/`basePrice`/`stock`
做 daily-diff，自動抓降價 / 缺貨 / 新品：
- 降價：`price` < 上次，或 `decals` 新增「限時特價/優惠特價」
- 缺貨：`stock.stockLevelStatus` → outOfStock
- 新品：新增 SKU 或 `decals` 新增「新品推薦/網路獨家」
複用 `backend/alerts.py` 的 `alert_for` / `scan` / `emit`；新邏輯接 `decals` 訊號。
驗收：用 `data/costco_catalog/products.full.json` 抽出含 decals 的樣本做離線 diff 測；
decal 變化能觸發對應警報、無變化時靜默。

### A3 — fallback（API 404 → 歷史快照，不 crash）
抓 catalog 失敗（HTTP 404 / 429 / 連線斷）時，回退到最新 `history_data.json` / 已存快照，
不 crash、不覆寫歷史、不發假警報；離線測（仿 `test_basket.py::test_basket_offline_returns_snapshot`）。
驗收：mock 404 → 回快照 + 明確 log「fallback 到快照」；歷史檔不被覆寫。

## 現況（先 recon 再補，勿重造）
- `backend/history.py`（888L）：`series`/`metrics`/`record`/`apply_window`/`discontinued_skus` 已有 diff 骨架。
- `backend/alerts.py`（479L）：`alert_for`/`scan`/`emit`/`alert_message`/`_verdict_emoji` 已有警報+sink(log/telegram/github)。
- `backend/scrapers.py`：`scrape_costco`/`fetch_price`/`parse_offers`。
- `backend/tests/`：180 個 pytest（py3.9.7 / pytest8.4.2），已有 `test_alerts`/`test_history`/`test_basket`/`test_watchlist`。
**先 grep 既有 `detectChange`/`detect`/`diff`/`decal` 邏輯 + 既有測試，確认真實 gap 才補**，
勿重造已覆蓋的；A1 三情境若已被 `test_history`/`test_alerts` 部分覆蓋，只補缺的情境與 decal 訊號。

## 硬約束
- 全離線：測試用 fixture / mock HTTP，**不觸真實 Costco API**（CI 離線安全）。
- 不碰 `src/lib/` 類 SSOT（後端無此限制，但保持改動聚焦 backend/）。
- 全 pytest 綠、無 regression（180 → 新增測試全綠）。
- **禁 `git clean` / 勿刪 untracked**（worktree 有 `pipeline/*.md`）；只 `git add` backend/ 下新增/修改檔。
- zh-TW、s2t；改動最小化、聚焦 Tier A。

## 跑法
```
cd <worktree>/backend && /Users/hermes-agent/Projects/price-monitor-pwa/backend/.venv/bin/python -m pytest -q
```
（venv 在主 worktree；共用 interpreter 即可，deps 齊全：fastapi/uvicorn/pydantic/pytest/httpx/bs4/lxml）
