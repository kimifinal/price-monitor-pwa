"""Pydantic schemas for the API + shared alert rule (the backend's SSOT)."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Item(BaseModel):
    id: str
    name: str
    target: float
    url: Optional[str] = None
    currency: str = "TWD"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PriceResult(BaseModel):
    id: str
    name: str
    target: float
    price: float
    alerted: bool
    checked_at: datetime = Field(default_factory=datetime.utcnow)


def should_alert(price: float, target: float) -> bool:
    """The single source of truth for the alert rule — mirrors
    `frontend/src/lib/monitor.js`'s `shouldAlert`. Keep the two in lockstep.
    """
    return price <= target


# --- historical price verdict (the compare rule for 歷史價格比價) ----------------
# The single source of truth for "is this a good time to buy?". Mirrors
# `frontend/src/lib/monitor.js`'s `priceVerdict`. Keep the two in lockstep.
# Threading a threshold through makes it tunable + testable in one place.
AT_LOW_TOL = 1.001   # "at the low" means within 0.1% of the all-time minimum
GOOD_DEAL_DROP = 15.0  # >= this % below the high => a genuinely good deal
NEAR_HIGH_DROP = 5.0   # <= this % below the high => basically at the high


def price_verdict(m: dict) -> dict:
    """Turn a sku's metrics (from history.metrics) into a human verdict.

    Returns {'verdict', 'label', 'drop_pct'}. Pure — no I/O. The thresholds are
    module constants so both sides (this + the JS mirror) can reference them and
    the tests pin them in one spot.
    """
    if not m or not m.get("points"):
        return {"verdict": "unknown", "label": "無歷史資料", "drop_pct": 0.0}

    drop = m.get("drop_pct_from_high", 0.0) or 0.0
    if m.get("at_all_time_low"):
        return {"verdict": "all_time_low", "label": "歷史最低 👍", "drop_pct": drop}
    if drop >= GOOD_DEAL_DROP:
        return {"verdict": "good_deal", "label": f"較近低點 ▼{drop:.0f}%", "drop_pct": drop}
    if drop <= NEAR_HIGH_DROP:
        return {"verdict": "near_high", "label": "接近高點", "drop_pct": drop}
    return {"verdict": "stable", "label": "平穩", "drop_pct": drop}
