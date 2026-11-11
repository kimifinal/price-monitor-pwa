"""
Price Monitor backend — FastAPI.

Exposes a small JSON API for the frontend PWA: watch items, fetch current
prices, and fire a Telegram alert when a price drops below target.

This is a SCAFFOLD: `scrapers.py` returns simulated prices. To make it real,
replace `fetch_price()` with an HTTP fetch against a product page + a parser,
and `alerts.py` already has a Telegram send stub you fill in.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

from models import Item, PriceResult, price_verdict
from scrapers import fetch_price
from alerts import send_telegram_alert
from costco import basket as costco_basket
import history


app = FastAPI(title="Price Monitor", version="1.0.0")

# In-memory store (swap for a real DB in production).
_store: List[Item] = []


class ItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target: float = Field(..., gt=0)
    url: Optional[str] = None
    currency: str = "TWD"


@app.post("/api/items", status_code=201, response_model=Item)
def create_item(payload: ItemIn) -> Item:
    item = Item(id=str(uuid.uuid4()), name=payload.name, target=payload.target,
                url=payload.url, currency=payload.currency)
    _store.append(item)
    return item


@app.get("/api/items", response_model=List[Item])
def list_items() -> List[Item]:
    return list(_store)


@app.get("/api/items/{item_id}")
def get_item(item_id: str) -> Item:
    for it in _store:
        if it.id == item_id:
            return it
    raise HTTPException(status_code=404, detail=f"item {item_id} not found")


@app.post("/api/items/{item_id}/check", response_model=PriceResult)
def check_item(item_id: str) -> PriceResult:
    """Poll one item's price, alert on drop. The alert decision here MUST use
    the SAME rule as the frontend's `monitor.js` — this is the shared "SSOT".
    """
    target = None
    for it in _store:
        if it.id == item_id:
            target = it
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")

    price = fetch_price(target.url or target.name)
    result = PriceResult(id=target.id, name=target.name, target=target.target,
                         price=price, alerted=price <= target.target)
    if result.alerted:
        send_telegram_alert(target, price)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


@app.get("/api/costco/basket")
def get_costco_basket(live: bool = False) -> dict:
    """Return today's 3C + 家電 basket.

    live=False: today's pre-snapshotted DEMO_BASKET (fast, offline, CI-safe).
    live=True:  real live scrape + BFS crawl (~30s, needs internet).
    """
    items = costco_basket(live=live)
    c3 = [p for p in items if p.get("tag") == "3C"]
    ca = [p for p in items if p.get("tag") == "家電"]
    return {
        "count": len(items),
        "3C": len(c3),
        "家電": len(ca),
        "items": items,
    }


# --- 歷史價格比價 --------------------------------------------------------------
# The time-series half. The history DB is pre-seeded (deterministic backfill
# from DEMO_BASKET) on first use so it is offline/CI-safe and immediate.
def _history_conn():
    """A connection to the local history DB, auto-seeded from the snapshot if
    empty. Resolves history.DEFAULT_DB at call time so tests can redirect it to
    a tmp file."""
    conn = history.connect()
    n = conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]
    if n == 0:
        from costco_data import DEMO_BASKET
        history.seed_from_snapshot(DEMO_BASKET, conn=conn)
    return conn


@app.get("/api/costco/history")
def get_costco_history() -> dict:
    """All tracked skus with comparison metrics + a verdict (the 比價 layer)."""
    conn = _history_conn()
    try:
        skus = [r["sku"] for r in conn.execute(
            "SELECT DISTINCT sku FROM observations ORDER BY sku").fetchall()]
        items = []
        for sku in skus:
            m = dict(history.metrics(sku, conn=conn))
            m["verdict"] = price_verdict(m)
            items.append(m)
    finally:
        conn.close()
    return {"count": len(items), "items": items}


@app.get("/api/costco/history/{sku}")
def get_costco_history_sku(sku: str) -> dict:
    """One sku's full series + metrics + verdict — what feeds the sparkline."""
    conn = _history_conn()
    try:
        m = dict(history.metrics(sku, conn=conn))
        series = history.series(sku, conn=conn)
    finally:
        conn.close()
    if m.get("points", 0) == 0:
        raise HTTPException(status_code=404, detail=f"no history for sku {sku}")
    m["verdict"] = price_verdict(m)
    m["series"] = [
        {"observed_at": ts, "price": price, "source": src_label}
        for (ts, price, src_label) in series
    ]
    return m
