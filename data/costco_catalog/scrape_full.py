#!/usr/bin/env python3
"""全量抓取 costco.com.tw 商品目錄 (currentPage 分頁, 增量落檔)"""
import urllib.request, json, time, os

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Chrome/120 Safari/605.1.15"
BASE = "https://www.costco.com.tw/rest/v2/taiwan/products/search?fields=FULL&query=1&pageSize=48&lang=zh_TW&curr=TWD"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(OUT_DIR, "products.full.json")
MAX_PAGE = 300  # 安全上限

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
    url = f"{BASE}&currentPage={pg}"
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "application/json",
                "Referer": "https://www.costco.com.tw/search?text=1"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            last = e; time.sleep(1.5 + a)
    return {"error": str(last), "products": []}

seen = {}
t0 = time.time()
page = 0
total_deals = 0
stop = False
last_save = 0
while page < MAX_PAGE and not stop:
    d = fetch_page(page)
    prods = d.get("products") or []
    if d.get("error"):
        print(f"  page {page}: ERR {d['error'][:60]}", flush=True)
    if not prods:
        print(f"  page {page}: empty -> stop", flush=True)
        stop = True
    for p in prods:
        sku = p.get("code")
        decraw = pf(p.get("decalData")); decals = []
        for dd in (decraw if isinstance(decraw, list) else []):
            val = dd.get("value") if isinstance(dd, dict) else None
            if isinstance(val, dict) and val.get("altText"):
                decals.append(val["altText"])
            elif isinstance(val, list):
                for vv in val:
                    if isinstance(vv, dict) and vv.get("value"):
                        av = vv["value"]
                        decals.append(av.get("altText") if isinstance(av, dict) else None)
        decals = [x for x in decals if x]
        price = pfi(p.get("price")); base = pfi(p.get("basePrice"))
        stockd = pf(p.get("stock"))
        seen[sku] = {
            "sku": sku, "name": p.get("name"), "englishName": p.get("englishName"),
            "price": price, "basePrice": base,
            "discount": (base - price) if (price and base and price < base) else 0,
            "discount_pct": round((1 - price/base)*100, 1) if (price and base and base > 0) else 0,
            "stock": stockd.get("stockLevelStatus") if isinstance(stockd, dict) else None,
            "warehouse": p.get("warehouseFulfilled"),
            "decals": decals, "category": None, "url": p.get("url"),
        }
        if seen[sku]["discount"] > 0:
            total_deals += 1
    page += 1
    # 每10頁增量落檔
    if page % 10 == 0 or prods == []:
        elapsed = time.time() - t0
        meta = {"source": "costco-com-tw-api",
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "pages_done": page, "products_unique": len(seen),
                "deals_detected": total_deals, "elapsed_min": round(elapsed/60, 1),
                "pagination_param": "currentPage", "status": "partial" if not stop else "complete"}
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"_meta": meta, "products": list(seen.values())}, f, ensure_ascii=False, indent=1)
        print(f"  [{elapsed/60:.1f}m] page {page-1} | unique={len(seen)} | deals={total_deals} | saved", flush=True)
    if prods and len(prods) < 48:
        stop = True
    time.sleep(0.2)

print(f"\n=== 完成: {page} pages, {len(seen)} products, {total_deals} deals ===", flush=True)
print(f"檔案: {OUT}", flush=True)
