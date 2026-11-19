# Tier B — MVM 檔期 vision 抽取 (B1 偵測 / B2 抽價 / B3 警報) + B4 UI

> 父 #35。Tier A(item 層 detectChange+decal+fallback, 6a2a367) 已落 master; 本案 = Tier B。
> 核心結論(§分工, 2026-11-17 實測): **MVM 檔期內容公開 API 一律 AccessDenied → 只能 vision 半自動**。
> 離線原則: 本 case 用**可注入 vision_fn + 合成 tile + p4.json schema 當 fixture** 測;
> 真實 vision(Playwright + LLM) 為 **out-of-CI** 路徑(文件化、不觸 CI)。

## 資料模型 (SSOT = data/costco_mvm/2026-11-16_mvm_p4.json; 真實已抓 122 筆 / 6 tab)
```
{ "tabs":[{"tab_id","label","period","url","price_type","description","n_products",
            "products":[ {"name","sku","orig","promo","discount","type","cat"} ]}],
  "price_types":{ "online_only", "store_online_diff", "store_only" } }
```
- 3 price types: online_only / store_online_diff / store_only
- manifest.json: 6 tabs(tab_id 推 url = content/{tab_id}); w1=66、3C/家電等
- **成本控制**: 只對新 / 變更 SKU 跑 vision —— 複用 Tier A `backend/detect_change.py` 的 diff, 不重造

## B1 偵測 new MVM tab (backend/mvm_detect.py)
- `detect_new_tabs(observed_tab_urls, manifest) -> [new tab_ids]`: 用 `manifest.tabs` 的 tab_id / url diff
- 「預測下一個新檔期」**不宣稱**(無公開訊號, §分工 已實證) —— 只偵測「已知 / 已觀察到的新 tab 出現」
- AC: manifest 6 tab, 餷第 7 url -> 偵測到新 tab; 餷原 6 -> 靜默(無誤報)

## B2 vision 抽價 module (backend/mvm_vision.py)
- `VisionFn` protocol: `call(tile_path, schema) -> {sku,name,orig,promo,discount,type,cat}`(**可注入**)
- `tile_screenshot(image_path, tile_h=600) -> [tile_paths]`: 座標 math; 合成長圖即可離線測
- `parse_and_assemble(tile_results, manifest) -> p4.json schema`: 組出每 tab 的 products[]
- `cost_control`: unchanged SKU **不呼叫** vision(複用 Tier A `detect_change` 的 diff); 新增 / 變更 SKU 才跑
- real vision provider: 文件化 `Playwright 截圖(screenshots/{tab}/) + LLM vision(MVM_VISION_PROVIDER env)`; out-of-CI
- AC(全離線): mock VisionFn + 合成 tile -> 組出**符合 p4.json schema**; unchanged SKU **不觸 vision**; 真實 provider 不被 CI 觸發; 禁 vision / Playwright 依賴進 CI, 全 fixture / mock

## B3 MVM 警報 (backend/mvm_alert.py; 複用 backend/alerts.py 的 scan/emit/alert_for, 不重造 dedup/sink)
- 新 MVM 檔期出現(B1 detect) -> 發 MVM 警報; MVM price drop(B2 products vs 上版 detect_change price_drop) -> 發 MVM 警報
- 複用 Tier A `detect_change.detect_change` + `alerts.scan`/`emit`/`alert_for`(dedup/sink/verdict 皆照搬)
- AC: 新 MVM tab -> alert 觸發; MVM price drop -> alert; 無變化 -> 靜默; fallback(無 snapshot) 不 crash / 不誤報

## B4 前端 MVM 頁 (Designer step, 確認後再 Coder; frontend/MvmCatalog.vue)
- 每檔期一頁: 圖片 / 品名 / 售價 / 折扣 / 類型 tag; 吃 MVM JSON(離線 baked, 仿 costco snapshot + SW)
- 設計須過 `frontend/scripts/sloplint.mjs` + `pipeline/design-anti-slop-gates.md`(「沒有 AI 美感的漂亮 UI」)
- 流程: Designer 渲 live PWA + 出 mockup -> 確認者核對 -> 凍結 token -> Coder 建 `MvmCatalog.vue` + App.vue view 切換
- **不在本 backend case**(獨立 UI PR; 本案只交付 B1/B2/B3 backend)

## 硬約束
- 全離線: fixture / mock HTTP + vision, 不觸真實 Costco API / 真實 vision / Playwright(CI 離線安全)
- 改動聚焦 `backend/`; 複用 Tier A `detect_change` / `alerts`; zh-TW/s2t
- **禁 git clean / 勿刪 untracked**; 只 `git add` backend/ + pipeline/ 新增檔(勿 stage 其他 untracked)
- 完成定義: `cd <worktree>/backend && ../../backend/.venv/bin/python -m pytest -q` 全綠(無 regression),
  新增測試確實覆蓋 B1 三情境 / B2 assembly+cost_control / B3 alert+fallback; ver 非 stub(74+ asserts、0 no-op)
