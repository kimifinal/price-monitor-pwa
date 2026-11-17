# #40 — 標題 emoji → 單色 SVG icon（清 sloplint 30a，維持 #24 invariant）

## Why
sloplint `30a`（heading 含 emoji / emoji 當 icon）抓出 6 個 FAIL：
App 四個 h2（🔔🎯📊📡）+ PriceHistory 兩處（🛒 來源、📊 verdict）。
#24 的 relabel invariant 又鎖死「emoji 字元做判別式」，所以 30a 不能盲刪——
要把判別式從「emoji 字元」遷到「icon 名」，維持 #24 的語意不變。

## Decision
換成一套 **16px 單色 line-icon**（`stroke=currentColor`、`fill=none`、一 name → 一 path），
取代彩色 emoji（#19/30a 的 AI-美感）。icon 用現成的 heading 字色，不引入第二套 icon 語言。
為了讓判別式從 emoji 字元遷到 icon 名，#24 invariant 改以 `name="…"` 斷言，語意 1:1 保留。

- 對齊 `frontend-aesthetic-engine`：monochrome / 克制、不花俏、走 token 的 `currentColor`。
- gate（⚙ U+2699）**不在** 30a 觸發範圍（sloplint 的 emoji 偵測器不抓技術符號），
  但為視覺一致，App/editor 的 gate 標題一併改用 gear icon + 改測試。

## Scope — 8 個位點（含 ⚙ 一致性）
| # | 檔案 | 舊 | 新 |
|---|---|---|---|
| 1 | App.vue:105 | `🔔 已觸發…` | `<icon name="bell"/> 已觸發…` |
| 2 | App.vue:115 | `🎯 手動追蹤…` | `<icon name="target"/> 手動追蹤…` |
| 3 | App.vue:127 | `⚙ 自動門檻 Gate…` | `<icon name="gear"/> 自動門檻 Gate…` |
| 4 | App.vue:135 | `📊 歷史價格…` | `<icon name="chart"/> 歷史價格…` |
| 5 | App.vue:145 | `📡 即時比價…` | `<icon name="signal"/> 即時比價…` |
| 6 | editor:147 | `⚙ 自動門檻 Gate…` | `<icon name="gear"/> 自動門檻 Gate…` |
| 7 | PriceHistory 來源 | `🛒 costco` | `<icon name="cart"/> costco`（`data-icon="source"`）|
| 8 | PriceHistory verdict | `📊 {{label}}` | `<icon name="chart"/> {{label}}` |

## 維持 #24 invariant（改判別式、不改語意）
- `🎯=manual` → `name="target"`：App 恰 1、editor 0。
- `⚙=gate` → `name="gear"`：App ≥1、editor ≥1。
- 舊字（`追蹤中` / `個人化`）仍消失（#24 原條件）。
- 新增 AC3 #40：App.vue 標題不再有 emoji。

## 不碰（別手滑）
- `WatchlistEditor.vue:258` `🔔 會觸發` we-fire span——有 `watchlist.test:253` 斷言、且非標題（30a 沒抓）。
- PriceHistory 只換 2 位點，verdict 邏輯 / sparkPath / format 全不動。
- `lib/*`、`backend/` 全不動（純 UI；gate 走 git-diff 證純 UI）。

## 驗證
`unit`+`e2e`+`lint`+`sloplint` 綠；sloplint 30a = 0（enforcer EXCLUDE 收掉 30a，留 20/48 deferred）；
e2e 全綠（無 emoji 硬斷言）；渲染 before/after 截圖人工確認「無 AI 美感」。
