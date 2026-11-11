"""SQLite price-history store — the time-series half of 歷史價格比價.

The basket snapshot gives ONE price point per SKU at a moment; to *compare*
prices we need a series over time. This module is that series:

  record()          append one observation per SKU when we (re)scrape
  seed_from_snapshot backfill a plausible 14-day series per SKU (deterministic,
                    marked synthetic) so the history API + tests are meaningful
                    without waiting real days or touching the network
  series(sku)       chronological (observed_at, price) points
  metrics(sku)      current / all-time-low / all-time-high / drop-from-high

Offline-safe: everything is a local SQLite file; tests use tmp_path or an
in-memory DB. No network, no real time required.
"""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "price_history.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  sku         TEXT    NOT NULL,
  name        TEXT,
  tag         TEXT,
  price       REAL    NOT NULL,
  currency    TEXT    DEFAULT 'TWD',
  observed_at TEXT    NOT NULL,          -- ISO-8601
  source      TEXT    DEFAULT 'costco',
  synthetic   INTEGER DEFAULT 0          -- 1 = deterministic backfill, not a real scrape
);
CREATE INDEX IF NOT EXISTS idx_obs_sku_time ON observations(sku, observed_at);
"""


# --------------------------------------------------------------------------
# connection
# --------------------------------------------------------------------------
def connect(path: Optional[str] = None) -> sqlite3.Connection:
    """Open (creating if needed) and init the schema. Returns a connection.

    `path=None` uses the DEFAULT_DB module global — resolved at call time so
    tests can monkeypatch `history.DEFAULT_DB` to an isolated tmp file.
    `path=':memory:'` gives an in-memory DB for tests.
    """
    if path is None:
        path = DEFAULT_DB
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------
def record(items: list[dict], source: str = "costco",
           synthetic: bool = False, ts: Optional[str] = None,
           conn: Optional[sqlite3.Connection] = None) -> int:
    """Append one observation per item, deduped by (sku, price, source, ts).

    Returns the number of rows actually inserted. Idempotent within a single
    scrape: re-recording the same basket at the same timestamp inserts nothing
    new (safe for a scheduler that may fire twice).
    """
    own = conn is None
    conn = conn or connect()
    cur = ts or datetime.now().isoformat()
    inserted = 0
    for item in items:
        sku = str(item.get("sku")) if item.get("sku") is not None else None
        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            continue
        if not sku:
            continue
        exists = conn.execute(
            "SELECT 1 FROM observations WHERE sku=? AND price=? AND source=? AND observed_at=? LIMIT 1",
            (sku, price, source, cur),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO observations (sku,name,tag,price,currency,observed_at,source,synthetic) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                sku,
                item.get("name"),
                item.get("tag"),
                price,
                item.get("currency", "TWD"),
                cur,
                source,
                1 if synthetic else 0,
            ),
        )
        inserted += 1
    if own:
        conn.commit()
    else:
        conn.commit()
    if own:
        conn.close()
    return inserted


def series(sku: str, conn: Optional[sqlite3.Connection] = None) -> list[tuple[str, float, str]]:
    """Chronological observations for a sku: list of (observed_at, price, source-flag)."""
    own = conn is None
    conn = conn or connect()
    rows = conn.execute(
        "SELECT observed_at, price, source FROM observations WHERE sku=? "
        "ORDER BY observed_at ASC",
        (str(sku),),
    ).fetchall()
    out = [(r["observed_at"], float(r["price"]), r["source"] or "costco") for r in rows]
    if own:
        conn.close()
    return out


def metrics(sku: str, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Derive comparison metrics from a sku's series.

    Returns {} for a sku with no history, else:
      current, low, high, drop_pct_from_high, at_all_time_low,
      points, first_seen, last_seen, name, tag.
    """
    own = conn is None
    conn = conn or connect()
    rows = conn.execute(
        "SELECT observed_at, price, name, tag FROM observations WHERE sku=? "
        "ORDER BY observed_at ASC",
        (str(sku),),
    ).fetchall()
    if own:
        conn.close()
    if not rows:
        return {"sku": str(sku), "points": 0}

    prices = [float(r["price"]) for r in rows]
    low = min(prices)
    high = max(prices)
    current = prices[-1]
    drop = ((high - current) / high * 100.0) if high else 0.0
    return {
        "sku": str(sku),
        "name": rows[-1]["name"] or "",
        "tag": rows[-1]["tag"] or "",
        "current": round(current, 2),
        "low": round(low, 2),
        "high": round(high, 2),
        "drop_pct_from_high": round(drop, 1),
        "at_all_time_low": current <= low * 1.001,
        "points": len(rows),
        "first_seen": rows[0]["observed_at"],
        "last_seen": rows[-1]["observed_at"],
    }


# --------------------------------------------------------------------------
# deterministic offline backfill (so the UI/tests have a series to show)
# --------------------------------------------------------------------------
def seed_from_snapshot(items: list[dict], days: int = 14,
                       now: Optional[datetime] = None,
                       conn: Optional[sqlite3.Connection] = None) -> int:
    """Backfill a deterministic 14-point daily series per SKU around its current
    price, ending exactly at the current price.

    Deterministic (seeded by sku) so tests are stable and it is safe to call
    repeatedly. Each SKU's walk starts ~15-30% above current and drifts down to
    it, so `current` lands near the all-time low — a realistic "is it a good
    time to buy now?" story, marked synthetic=1 (honest, not a real scrape).
    """
    own = conn is None
    conn = conn or connect()
    now = now or datetime.now()
    inserted = 0
    for item in items:
        sku = item.get("sku")
        price = item.get("price")
        if sku is None or price is None:
            continue
        rng = random.Random(str(sku))
        start = float(price) * (1.15 + rng.random() * 0.15)
        for d in range(days):
            frac = d / max(1, days - 1)
            base = start + (float(price) - start) * frac   # drift down to current
            noise = float(price) * 0.02 * (rng.random() - 0.5)
            p = round(base + noise, 2) if d < days - 1 else float(price)
            stamp = (now - timedelta(days=days - 1 - d)).isoformat()
            exists = conn.execute(
                "SELECT 1 FROM observations WHERE sku=? AND price=? AND observed_at=? LIMIT 1",
                (str(sku), p, stamp),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO observations (sku,name,tag,price,currency,observed_at,source,synthetic) "
                "VALUES (?,?,?,?,?,?,?,1)",
                (
                    str(sku),
                    item.get("name"),
                    item.get("tag"),
                    p,
                    item.get("currency", "TWD"),
                    stamp,
                    "backfill",
                ),
            )
            inserted += 1
    if own:
        conn.commit()
    else:
        conn.commit()
    if own:
        conn.close()
    return inserted
