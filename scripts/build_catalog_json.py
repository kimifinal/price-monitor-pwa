#!/usr/bin/env python3
"""Generate frontend/src/data/catalog.json from data/costco_catalog/products.full.json.

Keep only: sku, name, price, basePrice, discount, online_only (bool), stock.
online_only = True when 'Costco好市多網路獨家商品' is in decals.
Drop: englishName, url, category, warehouse, decals, discount_pct (recomputable).
Output shape: { products: [...] } with 10,049 items.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "costco_catalog", "products.full.json")
OUT = os.path.join(ROOT, "frontend", "src", "data", "catalog.json")

ONLINE_DECAL = "Costco好市多網路獨家商品"

with open(SRC, "r", encoding="utf-8") as f:
    raw = json.load(f)

products = raw.get("products", [])
out = []
for p in products:
    if not isinstance(p, dict):
        # normalize a malformed entry to a null-safe record
        p = {}
    decals = p.get("decals") or []
    online_only = ONLINE_DECAL in decals if isinstance(decals, list) else False
    out.append({
        "sku": p.get("sku"),
        "name": p.get("name") if p.get("name") is not None else "N/A",
        "price": p.get("price"),
        "basePrice": p.get("basePrice"),
        "discount": p.get("discount", 0),
        "online_only": bool(online_only),
        "stock": p.get("stock") if p.get("stock") is not None else "N/A",
    })

data = {"products": out}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

# Verify
n_total = len(out)
n_online = sum(1 for x in out if x["online_only"])
n_store = n_total - n_online
n_disc = sum(1 for x in out if (x.get("discount") or 0) > 0)
print(f"total={n_total} store={n_store} online={n_online} discount>0={n_disc}")
print(f"expected total=10049 store=5356 online=4693 discount>0=246")
assert n_total == 10049, f"total {n_total} != 10049"
assert n_store == 5356, f"store {n_store} != 5356"
assert n_online == 4693, f"online {n_online} != 4693"
assert n_disc == 246, f"discount {n_disc} != 246"
# confirm dropped fields are absent
sample = out[0]
assert set(sample.keys()) == {"sku", "name", "price", "basePrice", "discount", "online_only", "stock"}, sample.keys()
print("WROTE", OUT, os.path.getsize(OUT), "bytes")
