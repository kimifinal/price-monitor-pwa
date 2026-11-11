#!/usr/bin/env python3
"""Generate costco_data.py DEMO_BASKET from a JSON dump.

Usage: python gen_costco_data.py [items.json]
Defaults to /tmp/costco_costco_3c.json or reads stdin if no file.
"""
import json, os, datetime, sys

src = sys.argv[1] if len(sys.argv) > 1 else None
if src and os.path.exists(src):
    items = json.load(open(src, encoding="utf-8"))
else:
    items = json.load(sys.stdin)

# Normalize to fixed key order + fill defaults so DEMO_BASKET is uniform.
norm = []
for p in items:
    norm.append({
        "name": p.get("name") or "（無名）",
        "price": p.get("price", 0),
        "currency": p.get("currency", "TWD"),
        "sku": p.get("sku", "n/a"),
        "url": p.get("url", ""),
        "tag": p.get("tag", "其他"),
        "category_path": p.get("category_path", ""),
    })

by_tag = {}
for p in norm:
    by_tag[p["tag"]] = by_tag.get(p["tag"], 0) + 1
generated = datetime.date.today().isoformat()

header = f'''"""Offline snapshot of Costco 3C + 家電 PDP prices.

Refreshed {generated} via BFS crawl of Costco PDP "相關推薦" links
({by_tag.get("家電", 0)} 家電 + {by_tag.get("3C", 0)} 3C items, all real SKUs).
Used by the API (live=False default) and by the offline unit tests so CI stays
offline-safe and free of 429 limits.
"""

import os as _os

# JSON literal = valid Python (strings/numbers/lists). null never appears here
# because defaults fill every field.
DEMO_BASKET = '''

out = header + json.dumps(norm, ensure_ascii=False, indent=2) + '''

__all__ = ["DEMO_BASKET"]
'''

import pathlib
_out = pathlib.Path(__file__).resolve().parent / "costco_data.py"
with open(_out, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Rebuilt costco_data.py: {len(norm)} items ({by_tag})")
