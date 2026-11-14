# Price Monitor PWA

追蹤目標價、跌破就通知。這是一個**完整的 CI/CD + 全棧練習專案**：前後端、離線
PWA、單一真相來源（SSOT）、CI 門控全串起來。

> **現況（2026-11-12）**：7 張 issue 全部關閉、master 綠、離線 PWA 上線於
> [`kimifinal.github.io/price-monitor-pwa`](https://kimifinal.github.io/price-monitor-pwa/)。
> 抓取層是 Costco BFS 爬蟲（真價 + 離線 fallback），範圍**現階段只含 Costco**
> （加密貨幣已在設計中保留機器、但現階段移除，詳 §Roadmap）。
>
> **架構圖**：[`docs/architecture.html`](docs/architecture.html)（離線可開，dark theme）。

---

## 三大設計 invariant（這是專案的靈魂）

1. **真相來源 = git 可 diff 的 JSON，不是 .db。**
   時序、gate、去重三個 SSOT 都是版本控制的 JSON，`history_data.json` /
   `watchlist.json` / `alerts_state.json`。理由：可 diff、可回溯、
   二進位 SQLite 是 transient（`.gitignore` 掉，會汙染、不可 diff、不可移植）。
   API 啟動即把 JSON 重灌進 in-memory（快）——JSON 才是真相，**.db 永不當真相**。

2. **判定（verdict）只有一處。**
   `backend/models.py::price_verdict` 是唯一的判定標準，前端
   `frontend/src/lib/monitor.js::priceVerdict` 是它的**鏡像**。前後端共用一條規則，
   「跌破 / all_time_low / good_deal」永不漂移。

3. **離線安全（offline-safe）是硬 AC，不是可選。**
   所有抓取都有確定性 fallback（模擬價 / 快照），CI 在無網路（air-gapped）機器上
   仍能全綠。合成資料（`source != 'costco-real'`）**永不觸發告警**。

---

## 運行時數據流

```
外部 Costco PDP
   │  ① 真 HTTP 抓取 + 離線 fallback
   ▼
scrapers.py / costco.py   ── 快照 ──►  costco_data.py   (BFS「相關推薦」30 SKU 離線快照)
   │  ② 每批 append 真實點 / 缺日補合成回填 / 收 90 天滑窗
   ▼
history.py ──► history_data.json   ★ 時序 SSOT（git-diffable）
   │  ③ 計算 current / 歷史最低 / 跌破 % / drop-from-high
   ▼
models.price_verdict  ◄──►  monitor.js.priceVerdict      ★ 判定只一處（前後端鏡像）
   │  ④ 僅在 watchlist 內「且」達到自己門檻的 SKU 才放行
   ▼
watchlist.py  (gate)  ──► watchlist.json   ★ 個人化 gate（git-diffable，獨立於時序）
   │  ⑤ dedup（alerts_state.json）→ 每事件只通知一次
   ▼
alerts.py  scan/emit  ──►  sink:  log（預設，不污染） / github（issue 摘要） / telegram
```

### 前端 PWA（全離線）

`App.vue` → `PriceHistory / WatchlistEditor / ItemCard / AddItemForm` →
`sw.js` + `offline-cache.js`：service worker 預先快取 `/api/costco/history`
快照與 app shell，連 API 都離線可用。深色、edge-to-edge（`2b41034`）。

---

## 專案結構

```
price-monitor-pwa/
├── backend/                       FastAPI + pytest（後端 job）
│   ├── main.py                    路由 + history/verdict/gate/alerts 接上
│   ├── models.py                  ★ verdict 唯一真相來源；priceVerdict 的前端鏡像
│   ├── scrapers.py / costco.py    真 HTTP 抓取 + 離線 fallback（Costco BFS）
│   ├── costco_data.py             30 個真實 SKU 離線快照
│   ├── history.py                 時序：append / 合成回填 / 90 天滑窗保留
│   ├── watchlist.py               個人化 gate（watchlist.json，獨立於時序）
│   ├── alerts.py                  verdict 告警：dedup + 三 sink（log/telegram/github）
│   ├── history_data.json          ★ 時序 SSOT
│   ├── watchlist.json             ★ gate SSOT
│   ├── alerts_state.json          ★ 去重 SSOT
│   └── tests/                     10 個 pytest（含 retention / verdict 一致性 / dedup / gate）
├── frontend/                      Vue 3 + Vite PWA（前端 job）
│   ├── src/lib/monitor.js         ★ 前端 verdict 鏡像（守「同一條規則」）
│   ├── src/lib/{history,watchlist,offline-cache,storage}.js
│   ├── src/components/            PriceHistory / WatchlistEditor / ItemCard / AddItemForm
│   ├── src/sw.js                  離線 service worker
│   ├── public/snapshot/           給 SW 預快取的離線快照 JSON
│   └── tests/{unit,e2e}/         Vitest（8 檔 / 91 例）+ Playwright E2E（7 例）
├── scripts/
│   ├── refresh_snapshot.py        把抓取/時序渲染成前端快照 JSON
│   ├── render_history_snapshot.py 時序渲染（純 JSON，不碰 .db）
│   └── notify_alerts.py           CI 裡掃 verdict + 投遞（sink / token / chat）
├── .github/workflows/
│   ├── ci.yml                     兩條 job（frontend / backend），needs: 門控
│   └── refresh-costco.yml         排程刷新（cron '0 4 * * *'）+ 可選 sink
└── docker-compose.yml             可選的容器化跑法
```

---

## CI/CD 門控（`ci.yml`）

兩條 job 用 `needs:` 串成門控——**任一紅 → 後續全跳（queued→skip）**，後端 e2e
絕不在 lint 紅時執行：

| 層 | 前端 job（`frontend`） | 後端 job（`backend`） |
|---|---|---|
| Lint | ESLint（zero warning） | Ruff |
| Unit + Coverage gate | Vitest，**80% 門檻**（守 regression gate 的 baseline） | pytest，**80% 門檻** |
| E2E | Playwright：比價 / watchlist / 離線 smoke（7 例） | `TestClient` 打全路由 |
| Deploy | `deploy-frontend` → GitHub Pages（**阻斷式**，綠才部署） | 後端部署（Railway/Fly/VPS） |

`refresh-costco.yml` 每日 ~04:00 UTC 重抓真價 → 渲染快照 → 掃 verdict →
按 `sink`（預設 `log`，不污染；可選 `github`/`telegram`）投遞。

---

## 四角色開發 pipeline（本專案的開發方式）

```
Architect（你 + 我）          Coder          Reviewer          verdict（= CI exit code）
  定範圍 + AC                    實作          獨立 subagent       CI 綠才算數
        │                          實作            逐 AC + 實讀/實跑       ↑
        └──────── 4 張 issue 各自走這條線，每張都有「證明」 ─────────────┘
```

`verdict = CI 的 exit code`——不信 subagent 自陳的「我測過」（它可能幻覺全綠），
只用 CI 紅綠當判定。每張 issue 的證明 = 綠 CI + 實測輸出。

---

## 本地開發

```bash
# 前端（注意：系統 /usr/local node 壞了，用可攜 node）
export PATH="$HOME/.hermes/node/bin:$PATH"
cd frontend && npm install && npm run dev      # http://127.0.0.1:5173
npm run lint && npm run test:coverage && npm run test:e2e   # Playwright chromium 已預裝

# 後端
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python main.py                                  # uvicorn :8000
pytest -q                                       # 10 檔測試
```

## 容器化（Docker）

`docker-compose.yml` 起三個服務（build context = 專案根目錄）：

```
api      →  uvicorn :8000              (FastAPI 全路由 + JSON SSOT 在內存)
refresh  →  python scripts/refresh_snapshot.py   (一次任務，追加到 JSON SSOT)
render   →  python scripts/render_history_snapshot.py (一次任務，渲染 HTML)
```

```bash
# 一鍵起全棧（api + refresh + render）
docker compose up

# 背景執行
docker compose up -d

# 只看 API + 重構
docker compose up --build refresh

# 停 + 刪 volume
docker compose down -v
```

**Volume 語義**：`ssot-data` 掛載到 `/app/backend/ssot`，
`refresh` 的 JSON 更新會留在 volume 裡，`docker compose restart` 不丟。

**注意**：`.dockerignore` 排除 `node_modules / .git / .venv / **/*node_modules/`，
Dockerfile 只裝 `requirements.txt` + `uvicorn[standard]`。

---

## 上線

- **前端** → GitHub Pages：CI 的 `deploy-frontend` 綠即在 master 部署（已上線；
  Pages 來源 = GitHub Actions + `github-pages` Environment）。
- **告警投遞** → 預設 `sink=log`（排程跑不污染、不建立 issue）。要真正送到人手上，
  見下「#### 接 Telegram / GitHub 告警投遞（#9）」子節。
- **後端** → Railway / Fly.io / 自己的 VPS（`python main.py` 監聽 8000）。

#### 接 Telegram / GitHub 告警投遞（#9）

sink 預設 `log`（排程跑不污染、不建立 issue、不需任何 secret）。真正投遞只需把
credential 放進 **repo Secrets**（絕不進 repo），再用 workflow 的 `sink` input 選 sink：

1. 到 `Settings → Secrets and variables → Actions` 新增兩個 secret：
   - `TELEGRAM_BOT_TOKEN`（@BotFather 給的 token — 放 repo secret，**絕不**寫進任何檔案）
   - `TELEGRAM_CHAT_ID`（你的 chat / channel id — 同上）
   - GitHub sink 只用免費的 built-in `GITHUB_TOKEN`（`refresh-costco.yml` 已注入）。
2. 觸發 `refresh-costco.yml` 並選 `sink`：手動 dispatch 選 `sink=telegram`（或
   `sink=github`；留白 / 排程預設仍是 `log`，不投遞）。workflow 以 env 方式讀
   `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`（`secrets` 上下文的引用，非 literal），
   程式碼在缺 credential 時只 `log` 一則 skip notice 並回傳 0 —— CI 絕不會因缺
   secret 而紅，也**絕不把 token 印進 log**。dedup 靠 git-SSOT 的 `alerts_state.json`，
   每事件只投一次、一次只投一批 comment。

> **無密碼入庫護欄（#10 護欄，#9 強化）**：`.gitignore` 已擋 `.env*`（僅保留範本
> `.env.example`），no-secrets CI 也擋下任何 `.env*`（含 `.env.local` /
> `.env.production` / `.env.development` / `.env.dev`）、bare `token` / `secret` /
> `api_key` / `passwd`（任一配 8 字元以上 value）、以及 40 字元的 AWS secret ——
> 但**不會**誤報 `os.environ.get('TELEGRAM_BOT_TOKEN')` 這類裸變數參考（只有配上
> literal value 才變紅）。

---

## 現況 / Roadmap

### 已做（7 張 issue 全閉）
- #1 真實價格落地 SSOT　#2 警報 / 投遞（dedup + 三 sink）　#4 Watchlist（git-SSOT + 離線編輯）
- #5 保留策略（90 天滑窗 + 淘汰 sidecar）　#6 部署收尾 / 離線 PWA
- 手機 UI（#7）：watchlist 堆疊卡片 `2860b4c` + 無白邊補滿 `2b41034`
- Crypto 現階段移除（純 Costco 範圍）

### 待做（下一步可接）
- [x] **告警真正送到 Telegram / GitHub**（#9）：預設 `sink=log`（不污染）；`sink=telegram` 讀 repo secret 的 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`；`sink=github` 用免費 `GITHUB_TOKEN` 投摘要 comment（dedup 每事件一次）。詳上「接 Telegram / GitHub 告警投遞」子節。
- [ ] **Watchlist 可攜**（現只存 localStorage，換裝置/清快取會丟）
- [ ] **`.db` 汙染護欄**（CI 加「無密碼入庫 + history_data.json 重跑 byte 一致」）
- [ ] 容器化跑法（`docker-compose.yml` 已起，待擴）
- [ ] **加密貨幣**（機器仍在 `history.py`，現階段排除；要開就接時序 + 重啟 CI）

### 兩個已踩過的坑（供日後避開）
- **`.db` 汙染**：曾因 gitignored 的 `price_history.db` 殘留舊資料被 API/快照載入——
  修法：API 啟動只信任 JSON SSOT，`.db` 永不當真相。
- **判定漂移**：告警規則若前後端各寫一份會漂移——修法：`price_verdict` 只一處，
  前端是鏡像，前後端測試互守。
