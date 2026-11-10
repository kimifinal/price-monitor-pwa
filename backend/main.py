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

from models import Item, PriceResult
from scrapers import fetch_price
from alerts import send_telegram_alert

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
