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

import json
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


# --------------------------------------------------------------------------
# persistence — the git-tracked source of truth (history_data.json)
# --------------------------------------------------------------------------
# SQLite is the *runtime query engine*; the persisted source of truth a
# scheduled job appends to and commits is a JSON artifact. We use JSON (not a
# committed binary .db) because it is diffable, audit-friendly and merge-free —
# a single-writer daily job needs none of git's binary merge machinery, but a
# human can read exactly what changed.
PERSIST_PATH = os.path.join(os.path.dirname(__file__), "history_data.json")


def load_observations(path: str = PERSIST_PATH) -> list[dict]:
    """Read the persisted observation list. [] when the file is absent."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def export_observations(conn: sqlite3.Connection, path: str = PERSIST_PATH,
                        sort: bool = True) -> int:
    """Write all rows in `conn` to the JSON artifact. Returns row count.

    Deterministic ordering (observed_at, sku, price) so the file diff is
    stable across runs — a no-change day produces a byte-identical file.
    """
    q = ("SELECT sku,name,tag,price,currency,observed_at,source,synthetic "
         "FROM observations")
    if sort:
        q += " ORDER BY observed_at ASC, sku ASC, price ASC"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    for r in rows:
        r["sku"] = str(r["sku"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return len(rows)


def replay(conn: sqlite3.Connection, observations: list[dict]) -> int:
    """Insert a list of persisted observations into a DB, idempotently
    (dedupe by the natural key sku+observed_at+price+source). Returns added."""
    added = 0
    for o in observations:
        sku, ts, price = str(o.get("sku")), o.get("observed_at"), o.get("price")
        if sku is None or ts is None or price is None:
            continue
        dup = conn.execute(
            "SELECT 1 FROM observations WHERE sku=? AND observed_at=? AND price=? AND source=? LIMIT 1",
            (sku, ts, float(price), o.get("source", "costco")),
        ).fetchone()
        if dup:
            continue
        conn.execute(
            "INSERT INTO observations (sku,name,tag,price,currency,observed_at,source,synthetic) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                sku,
                o.get("name"),
                o.get("tag"),
                float(price),
                o.get("currency", "TWD"),
                ts,
                o.get("source", "costco"),
                1 if o.get("synthetic") else 0,
            ),
        )
        added += 1
    conn.commit()
    return added


def dump_observations(observations: list[dict],
                      path: str = PERSIST_PATH) -> int:
    """Write an observation list to the JSON artifact, ordered for a stable diff.

    The artifact is the single source of truth, so its byte output must be
    deterministic: sort by (sku, observed_at, synthetic) and indent with stable
    ASCII. This keeps the git diff reviewable (append-only: real points grow it).
    """
    ordered = sorted(
        observations,
        key=lambda o: (str(o.get("sku", "")), o.get("observed_at", ""),
                       int(o.get("synthetic", 0))),
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=1)    # matches export_observations
    return len(ordered)


def append_real(items: list[dict], today: Optional[str] = None,
                persist_path: str = PERSIST_PATH) -> int:
    """Grow the JSON time series with today's *real* price per sku.

    Loads the committed artifact, appends one real (non-synthetic) observation
    per sku dated today, and rewrites it. Re-runs the same day are no-ops (the
    (sku, date) key dedupes); a new day extends the series. This keeps
    history_data.json — not a binary .db — as the persisted SSOT, so it survives
    ephemeral CI runners. Returns the number of new points added (excludes skips).
    """
    obs = load_observations(persist_path)
    ts = (today or datetime.now().strftime("%Y-%m-%d")) + "T00:00:00"
    seen = {str(o.get("sku", "")) + "|" + o.get("observed_at", "") for o in obs}
    added = 0
    for item in items:
        price = item.get("price")
        if not price or price <= 0:
            continue
        sku = str(item.get("sku") or item.get("name"))
        key = sku + "|" + ts
        if key in seen:
            continue
        obs.append({
            "sku": sku,
            "name": item.get("name"),
            "tag": item.get("tag"),
            "price": float(price),
            "currency": item.get("currency", "TWD"),
            "observed_at": ts,
            "source": "costco",
            "synthetic": 0,
        })
        seen.add(key)
        added += 1
    if added:
        dump_observations(obs, persist_path)
    return added


def ensure_history(conn: Optional[sqlite3.Connection] = None,
                   persist_path: str = PERSIST_PATH,
                   fallback_items: Optional[list[dict]] = None) -> sqlite3.Connection:
    """Open a history DB populated from the PERSISTED artifact, falling back to a
    snapshot backfill only when the artifact is missing/empty.

    This is the API entry point: the service reads whatever a scheduled job last
    committed (real observations accumulated over time); a brand-new checkout
    with no artifact yet still shows a deterministic backfill demo.
    """
    own = conn is None
    conn = conn or connect()
    obs = load_observations(persist_path)
    if obs:
        replay(conn, obs)
    elif fallback_items:
        seed_from_snapshot(fallback_items, conn=conn)
    # Do NOT close a freshly-created conn: callers keep querying it (the API closes
    # in its own finally). We only close a conn we were *given* back closed — never.
    return conn


if __name__ == "__main__":
    # `python history.py` : bootstrap the persisted artifact when it is missing.
    # Used by the refresh cron on a *fresh checkout*. It must be deterministic and
    # idempotent, so the baseline is built in a fresh in-memory DB (not the
    # on-disk one, which could hold a stale/accumulated seed). If the JSON already
    # exists it is left untouched — the committed artifact is the SSOT.
    obs = load_observations()
    if len(obs) == 0:
        c = connect(":memory:")                 # fresh, ignores any on-disk db
        from costco_data import DEMO_BASKET
        seed_from_snapshot(DEMO_BASKET, conn=c)
        n = export_observations(c, PERSIST_PATH)
        c.close()
        print(f"history_data.json: {n} observations seeded "
              f"(at {PERSIST_PATH})")
    else:
        print(f"history_data.json: {len(obs)} observations already present "
              f"({PERSIST_PATH}) — left as-is")

