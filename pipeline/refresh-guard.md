# Spec: 排程快照「真的落地」護欄 (issue #12)

## 1. 背景 / 目標
`refresh-costco.yml` 有 `cron '0 4 * * *'`,但**沒有驗證每日真的把真實 costco 價落進
`history_data.json`**。若抓取靜默失敗(靜默 crawl fail),監控會停滯而無人知 —— 這正是一個
「盲區」,要讓它**可自證**(同 #15 可觀測性、#16 探活 gate 的精神)。

目標:每次 refresh 後,以**可斷言 + 可讀**的方式證明「真的新增了真實點」,若沒新增就**響響**
(不靜默),並留下一個「最後成功刷新時間」SSOT。

## 2. 現況(讀自 repo,勿改 SSOT)
- `backend/history_data.json`:一個 **git 追蹤、append-only** 的 JSON array,每筆觀察:
  `{sku, name, tag, price, currency, observed_at, source, synthetic}`。
  **真實點** = `source == "costco"` 且 `synthetic == 0`;`synthetic == 1` / `source == "backfill"`
  是人工補點,**不**算真實落地。
- `scripts/refresh_snapshot.py`:cron refresh 的執行路 —— 抓取 + 重生成 + 把**今日的真實觀察
  append 進 `history_data.json`** + (若有更動)commit/push。它**已離線安全**(靜默抓取失敗時
  保留既有 artifact)。
- `git diff HEAD -- backend/history_data.json` 在 refresh step 之後會顯示新 append 的行
  (refresh step 在 mutates worktree、commit 之前)。

## 3. 護欄邏輯(純函式 + 可測)
新增 `backend/stall_guard.py`,核心純函式(無 I/O、無網路、無 .db):

```
detect_new_real(prev_rows, cur_rows) -> {landed: bool, new_count: int, new_last_observed_at: str|None,
                                         prev_last_observed_at: str|None, prev_count: int, cur_count: int}
```
- 「new real point」= `src==costco 且 synthetic==0` 且 `observed_at > prev_last_real_observed_at`
  (pre-refresh 的 git HEAD 狀態為基線)。用 `observed_at` 的時間順序,不是 array 順序。
- `landed = new_count > 0`。
- 也提供 `format_report(result, prev_ts) -> str`,輸出人類可讀的一行:
  - landed:  `✅ [stall-guard] 本次落地 N 個真實 costco 點;last_real=<ts>;SSOT 已更新`
  - 未落地:  `⚠️  [stall-guard] 本次無新真實 costco 點 —— 抓取可能靜默失敗/停滯;歷史自 <prev_ts> 以來未變`

## 4. 「最後成功刷新時間」SSOT(一處寫、一處讀)
新增 `backend/refresh_state.json`(git 追蹤、可 diff):
```
{
  "updated_at":           <iso8601, 本次成功落地的時間>,
  "last_real_observed_at":<最新真實點的 observed_at>,
  "last_real_count":      <累積真實 costco 點總數>,
  "new_real_this_run":    <int, 本次新增>,
  "guard_version":        "1",
  "source": "backend/stall_guard.py issue #12"
}
```
- **唯一寫者**:stall-guard 在「本次有落地(landed)」時才更新它。
- **唯一讀者**:CI 探測 / 人類 `cat backend/refresh_state.json`。
- 未落地時**不**覆寫(`updated_at` 保持上次成功時間 —— 讓「停滯多久」一眼可見)。

## 5. CI 接線(`refresh-costco.yml`)
在 refresh step 之後、scan/alert step 之前,加一個 `stall-guard` step:
1. 讀 refresh **前**的基線:`git show HEAD:backend/history_data.json`(本次 run 的 committed 版)。
2. 讀 refresh **後**的 worktree `backend/history_data.json`。
3. 跑 `stall_guard.detect_new_real(prev, cur)` + `format_report`。
4. 印 `[stall-guard]` 那一行(**響**,CI log 可自證落地/沒落地)。
5. `landed` 時:更新 `refresh_state.json` 並 `git add` + 讓 refresh 的既有 commit 帶走它
   (或 guard step 自 commit `chore(stall-guard)[#12]: record last refresh`)。
6. **未落地**:預設發 **WARNING(响亮、入 log、入 SSOT 不覆寫)**;可選 `STALL_GUARD_FAIL=1` env
   (或 `--fail`)**改成 hard fail**。預設 **不**hard-fail —— 因為「某日真的沒有新價(例如 Costco
   當日無更新)」是合法的,不該 RED 掉每日 cron;要的是「不靜默」(响亮 + 可自證),不是「任何空日
   都掛」。此為**刻意的设计决定**,在 issue #12 備註。

## 6. 驗收表(對 #12 AC)
- [ ] AC1 guard:refresh 後 assert `history_data.json` 的真實點(`source=costco`)ts/數量有更新
      → `detect_new_real` 的 `landed` 為真當且有新點;CI log 印 `[stall-guard] ✅`。
- [ ] AC2 無新真實點 → CI 發 WARNING(預設,不靜默);`--fail` 時 fail。
- [ ] AC3 「最後成功刷新時間」可查:`refresh_state.json`(一處寫、一處讀)。
- [ ] 全部新離線 unit test(fixture prev/cur history,**無網路 / 無 .db / 無真抓取**)。
- [ ] **不**動 `should_alert` / `price_verdict` / `models.py` 等既有 SSOT 模組。
- [ ] `refresh-costco.yml` 維持離線安全 + cron `0 4 * * *` 不變。

## 7. 範圍 / 不做
- 不改抓取邏輯(`refresh_snapshot.py` 抓取部分);只在 refresh 之後**加**一個 guard step + 護欄模組。
- 不重構 `alert_state`。stall_guard 是獨立模組 + 獨立 step。
- 預設 WARNING、選配 hard-fail(見 §5.6);不要預設 hard-fail 掉每日 cron。
