# Price Monitor PWA

追蹤目標價、跌破就通知。這是一個**練習 CI/CD 的完整專案**——前後端都有，
CI pipeline 把 Lint / Unit / Coverage gate / E2E / Deploy 全串起來。
（沿用 mini-calculator 學到的 pipeline 結構，加上前後端兩條 job 串接。）

## 結構
```
price-monitor-pwa/
├── frontend/            Vue 3 + Vite PWA（含 PWA manifest + service worker）
│   ├── src/lib/monitor.js   ← 唯一真相來源：告警判斷，前端後端共用
│   ├── tests/unit/          Vitest 單元測試（守 80% coverage gate）
│   └── tests/e2e/           Playwright E2E
├── backend/             Python FastAPI（模擬 scrape + Telegram 通知）
│   ├── models.py              ← should_alert：與前端 monitor.js 同一條規則
│   └── tests/               pytest
└── .github/workflows/ci.yml ← 兩條 job（frontend / backend）用 needs: 串接
```

## 為什麼要建這個
- **前端** 與 **後端** 都有 lint + test + coverage gate——同一套流程，兩種語言。
- `needs:` 把 job 串成門控：後端 e2e 不會在 lint 紅時執行（queued→skip）。
- Coverage 門檻是**回歸門**而非破門：設在 baseline 之下，正常綠、退步就紅。

## 本地開發
```bash
# 前端
cd frontend && npm install && npm run dev   # http://127.0.0.1:5173

# 後端
cd backend && pip install -r requirements.txt && python main.py
# 測試
cd frontend && npm run lint && npm run test:coverage && npm run test:e2e
cd backend  && pytest -q
```

## 上線
- 前端 → GitHub Pages（CI 的 `deploy-frontend` 已在 master/main 觸發）
- 後端 → Railway / Fly.io / 你自己的 VPS（`python main.py` 監聽 8000）
- 填入 `backend/.env` 的 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 讓通知真的會觸發

## TODO（讓它變成真專案）
- [ ] 替換 `scrapers.py` 的模擬價格，改成真實 HTTP fetch + 解析
- [ ] 把 in-memory store 換成 PostgreSQL（加 `docker-compose` 的 db service）
- [ ] 前端輪詢改 websocket 即時推送
- [ ] 加入 cron：每 N 小時跑一次全量 check
