#!/usr/bin/env python3
"""全量抓取 costco.com.tw 完整目錄 (空 query + pageSize=100, currentPage 分頁)
- 空 query 回全量 10,049; 用 query=1 只回 8,458 (關鍵字檢索漏 ~1,591 筆)
- pageSize=100 只需 ~101 頁; 增量落檔 + retries 防 300s kernel timeout
"""
import urllib.request, json, time, os

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Chrome/120 Safari/605.1.15"
# 空 query 才回全量; pageSize=100 只需 ~101 頁
BASE = "https://www.costco.com.tw/rest/v2/taiwan/products/search?fields=FULL&query=&pageSize=100&currentPage={pg}&lang=zh_TW&curr=TWD"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "products.full.json")
MAX_PAGE = 300

def pf(v):
    if v is None: return None
    if isinstance(v, dict): return v
    if isinstance(v, str):
        try: return json.loads(v)
        except: return v
    return v
def pfi(v):
    d = pf(v); return d.get("intValue") if isinstance(d, dict) else None

def fetch_page(pg, retries=3):
    url = BASE.format(pg=pg)
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json",
                "Referer": "https://www.costco.com.tw/search"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            last = e; time.sleep(1.5 + a)
    return {"error": str(last), "products": []}

# 載入既有做基底, 疊加補全 (避免重複重算)
seen = {}
if os.path.exists(OUT):
    try:
        for p in json.load(open(OUT, encoding="utf-8")).get("products", []):
            seen[p["sku"]] = p
    except: pass
print(f"既有基底 {len(seen)} 筆, 開始補全全量...", flush=True)

t0 = time.time()
pg = 0
try:
    while pg < MAX_PAGE:
        d = fetch_page(pg)
        prods = d.get("products") or []
        if d.get("error"):
            print(f"  page {pg}: ERR {d['error'][:60]}", flush=True)
        if not prods:
            print(f"  page {pg}: empty -> stop", flush=True)
            break
        for p in prods:
            sku = p.get("code")
            if not sku:
                continue
            decraw = pf(p.get("decalData")); decals = []
            for dd in (decraw if isinstance(decraw, list) else []):
                val = dd.get("value") if isinstance(dd, dict) else None
                if isinstance(val, dict) and val.get("altText"):
                    decals.append(val["altText"])
                elif isinstance(val, list):
                    for vv in val:
                        if isinstance(vv, dict) and vv.get("value"):
                            av = vv["value"]; decals.append(av.get("altText") if isinstance(av, dict) else None)
            decals = [x for x in decals if x]
            price = pfi(p.get("price")); base = pfi(p.get("basePrice"))
            stockd = pf(p.get("stock"))
            seen[sku] = {"sku": sku, "name": p.get("name"), "englishName": p.get("englishName"),
                "price": price, "basePrice": base,
                "discount": (base - price) if (price and base and price < base) else 0,
                "discount_pct": round((1 - price/base)*100, 1) if (price and base and base > 0) else 0,
                "stock": stockd.get("stockLevelStatus") if isinstance(stockd, dict) else None,
                "warehouse": p.get("warehouseFulfilled"), "decals": decals,
                "category": None, "url": p.get("url")}
        pg += 1
        if pg % 5 == 0:
            elapsed = time.time() - t0
            deals = sum(1 for p in seen.values() if p.get("discount", 0) > 0)
            meta = {"source": "costco-com-tw-api", "query": "", "pageSize": 100,
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                    "pages_done": pg, "products_unique": len(seen),
                    "deals_detected": deals, "elapsed_min": round(elapsed/60, 1),
                    "pagination_param": "currentPage", "status": "partial"}
            json.dump({"_meta": meta, "products": list(seen.values())},
                      open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  [{elapsed/60:.1f}m] page {pg-1} | unique={len(seen)} | deals={deals} | saved", flush=True)
        if len(prods) < 100:
            print(f"  last page ({len(prods)}<100) at page {pg-1}, stop", flush=True)
            break
        time.sleep(0.2)
except Exception as e:
    print(f"  STOP: {e}", flush=True)

# 最終強制落檔 (防最後一屏丟失)
elapsed = time.time() - t0
deals = sum(1 for p in seen.values() if p.get("discount", 0) > 0)
meta = {"source": "costco-com-tw-api", "query": "", "pageSize": 100,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "pages_done": pg, "products_unique": len(seen),
        "deals_detected": deals, "elapsed_min": round(elapsed/60, 1),
        "pagination_param": "currentPage", "status": "complete"}
json.dump({"_meta": meta, "products": list(seen.values())},
          open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n=== 完成: {pg} pages | {len(seen)} products | {deals} 折扣 | status=complete ===", flush=True)
print(f"檔案: {OUT} ({os.path.getsize(OUT)/1024/1024:.1f} MB)", flush=True)
