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
