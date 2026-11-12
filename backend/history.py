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
        "SELECT observed_at, price, name, tag, synthetic FROM observations WHERE sku=? "
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
    # "current" = the price the verdict is actually about. A real scraped
    # observation outranks a deterministic backfill point, so when real data
    # exists the headline never reflects the synthetic shape. Only when no real
    # point has ever been recorded do we fall back to the latest backfill value.
    real_rows = [r for r in rows if not int(r["synthetic"])]
    cur_rows = real_rows if real_rows else rows
    current = float(cur_rows[-1]["price"])
    drop = ((high - current) / high * 100.0) if high else 0.0
    return {
        "sku": str(sku),
        "name": cur_rows[-1]["name"] or "",
        "tag": cur_rows[-1]["tag"] or "",
        "current": round(current, 2),
        "current_is_real": bool(real_rows),
        "low": round(low, 2),
        "high": round(high, 2),
        "drop_pct_from_high": round(drop, 1),
        "at_all_time_low": current <= low * 1.001,
        "points": len(rows),
        "real_points": len(real_rows),
        "first_seen": rows[0]["observed_at"],
        "last_seen": cur_rows[-1]["observed_at"],
    }


# --------------------------------------------------------------------------
# deterministic offline backfill (so the UI/tests have a series to show)
# --------------------------------------------------------------------------
def seed_from_snapshot(items: list[dict], days: int = 14,
                       now: Optional[datetime] = None,
                       conn: Optional[sqlite3.Connection] = None,
                       source: str = "backfill") -> int:
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
                    source,
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
# A SEPARATE, decoupled sidecar for discontinued (orphan) skus. It holds the LAST
# known observation of any sku the rolling window evicted outright, so the alert
# scanner / watchlist can still reference a sku that has dropped out of the series
# — no dangling row, no silent deletion. watchlist.json is NEVER rewritten by this
# (that is the #4 decoupling; retention only *flags* a discontinued watched sku).
DISCONTINUED_PATH = os.path.join(os.path.dirname(__file__), "history_data.discontinued.json")

# -------- rolling-window retention (issue #5: 保留策略 / drift 衛生) --------
# history_data.json is append-only (reals grow it every day) so without a bound it
# grows without bound. A rolling window keeps only the most recent N days. N is
# configurable via the HISTORY_WINDOW_DAYS env var, an arg, or a param. The window
# is ANCHORED at the newest observation in the file by default (NOT the wall clock)
# so re-running a refresh on the already-pruned file is byte-identical — the
# "idempotent + deterministic diff" guarantee (#5 AC4). When a window must evict,
# it drops OLD SYNTHETIC (backfill) points first and keeps REAL points (a real
# observation outranks an equivalent-age synthetic, #5 AC2); a sku left with no
# in-window point and no real point is marked "discontinued" (#5 AC3), never left
# as an orphan row.
DEFAULT_WINDOW_DAYS = 90
ENV_WINDOW = "HISTORY_WINDOW_DAYS"


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
                      path: str = PERSIST_PATH,
                      window_days: "Optional[int]" = None,
                      now=None) -> int:
    """Write an observation list to the JSON artifact, ordered for a stable diff.

    The artifact is the single source of truth, so its byte output must be
    deterministic: sort by (sku, observed_at, synthetic) and indent with stable
    ASCII. This keeps the git diff reviewable (append-only: real points grow it).

    When `window_days` is given the list is first passed through `apply_window`
    (the rolling-window retention, #5 AC1) so the file stops growing without bound.
    `window_days=None` (the existing default) leaves behavior unchanged, which keeps
    every pre-#5 call site and test intact. `now` anchors the window (defaults to
    the newest observation in the list for a wall-clock-independent diff — #5 AC4).
    """
    if window_days is not None:
        observations = apply_window(observations, window_days=window_days, now=now)
    ordered = sorted(
        observations,
        key=lambda o: (str(o.get("sku", "")), o.get("observed_at", ""),
                       _syn_int(o)),
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=1)    # matches export_observations
    return len(ordered)


def append_real(items: list[dict], today: Optional[str] = None,
                persist_path: str = PERSIST_PATH,
                source: str = "costco", synthetic: bool = False) -> int:
    """Grow the JSON time series with today's observation per sku — for ANY source.

    Loads the committed artifact, appends one observation per sku dated today
    (a *real* scrape by default; pass `synthetic=True` for a deterministic
    backfill point), and rewrites it deterministically. Re-running the same day
    for the same source is a no-op (deduped by sku+date+source), so a second
    source can grow the SAME `history_data.json` without clobbering the first
    source's point at the same (sku, day). A per-item `source`/`synthetic`
    override the module defaults, so an alternate source's points land beside the
    primary source's. Returns the new points added.
    """
    obs = load_observations(persist_path)
    ts = (today or datetime.now().strftime("%Y-%m-%d")) + "T00:00:00"
    # multi-source dedup key: two different sources may share a (sku, day)
    # without clobbering each other.
    seen = {f"{o.get('sku')}|{o.get('observed_at')}|{o.get('source', 'costco')}"
            for o in obs}
    added = 0
    for item in items:
        price = item.get("price")
        if not price or price <= 0:
            continue
        sku = str(item.get("sku") or item.get("name"))
        src = item.get("source", source)
        syn = item.get("synthetic", synthetic)
        key = f"{sku}|{ts}|{src}"
        if key in seen:
            continue
        obs.append({
            "sku": sku,
            "name": item.get("name"),
            "tag": item.get("tag"),
            "price": float(price),
            "currency": item.get("currency", "TWD"),
            "observed_at": ts,
            "source": src,
            "synthetic": 1 if syn else 0,
        })
        seen.add(key)
        added += 1
    if added:
        dump_observations(obs, persist_path)
    return added


def ensure_history(conn: Optional[sqlite3.Connection] = None,
                   persist_path: str = PERSIST_PATH,
                   fallback_items: Optional[list[dict]] = None,
                   extra_items: Optional[list[dict]] = None) -> sqlite3.Connection:
    """Open a history DB populated from the PERSISTED artifact, falling back to a
    snapshot backfill only when the artifact is missing/empty.

    This is the API entry point: the service reads whatever a scheduled job last
    committed (real observations accumulated over time); a brand-new checkout
    with no artifact yet still shows a deterministic backfill demo.

    `extra_items` makes the layer *multi-source*: when supplied, any sku that has
    no series yet gets a deterministic, synthetic backfill (source='backfill') so
    an alternate source coexists in the SAME series + verdict layer even before a
    single real scrape. Backfill stays synthetic so the real-only alert scanner
    can never fire on it.
    """
    own = conn is None
    conn = conn or connect()
    obs = load_observations(persist_path)
    if obs:
        replay(conn, obs)
    elif fallback_items:
        seed_from_snapshot(fallback_items, conn=conn)
    if extra_items:
        have = {str(r["sku"]) for r in conn.execute(
            "SELECT DISTINCT sku FROM observations").fetchall()}
        missing = [c for c in extra_items if str(c.get("sku")) not in have]
        if missing:
            seed_from_snapshot(missing, conn=conn, source="backfill")
    # Do NOT close a freshly-created conn: callers keep querying it (the API closes
    # in its own finally). We only close a conn we were *given* back closed — never.
    return conn


def all_sellers(conn: Optional[sqlite3.Connection] = None) -> list[str]:
    """Distinct skus currently tracked, stably ordered.

    The single enumerator: both the `/api/costco/history` endpoint and the alert
    scanner call this, so they always see the same set of SKUs to evaluate.
    """
    own = conn is None
    conn = conn or connect()
    rows = conn.execute("SELECT DISTINCT sku FROM observations ORDER BY sku").fetchall()
    skus = [str(r["sku"]) for r in rows]
    if own:
        conn.close()
    return skus


# --------------------------------------------------------------------------
# rolling-window retention — issue #5 (保留策略 / drift 衛生)
#
# history_data.json is append-only, so it grows without bound. `apply_window` adds
# a deterministic, IDEMPOTENT rolling-window prune anchored at the NEWEST
# observation (not the wall clock): evict old points, but drop SYNTHETIC (backfill
# / fallback) points before equivalent-age REAL points, and mark a sku "discontinued"
# (sidecar record, never a dangling row) when its whole series falls out of window
# and it has no real evidence. `prune_to_window` wires it into the refresh path.
# --------------------------------------------------------------------------
def _syn_int(o: dict) -> int:
    """Normalise the synthetic flag to 0/1 across int / bool / str spellings."""
    syn = o.get("synthetic", 0)
    if isinstance(syn, bool):
        return 1 if syn else 0
    if isinstance(syn, str):
        return 1 if syn.strip().lower() in ("1", "true", "yes") else 0
    try:
        return 1 if int(syn) else 0
    except (TypeError, ValueError):
        return 0


def _is_real(o: dict) -> bool:
    """A genuine scrape is the NOT-synthetic one (a real outranks backfill/fallback)."""
    return _syn_int(o) == 0


def _parse_ts(ts):
    """Parse an ISO-8601 `observed_at` to a NAIVE datetime, tolerant of 'Z',
    offsets, and date-only forms — uniform naive across py3.9/3.11 so all
    window comparisons are safe."""
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=None)
            except ValueError:
                continue
        raise
    return dt.replace(tzinfo=None)


def _obs_ts_key(o: dict):
    """Stable sort/compare key for an observation's timestamp (naive datetime)."""
    return _parse_ts(o.get("observed_at", ""))


def newest_ts(observations: list[dict]):
    """The most recent observed_at across all observations (naive datetime), or
    None for an empty/corrupt list — the window's default anchor."""
    best = None
    for o in observations:
        raw = o.get("observed_at") if isinstance(o, dict) else None
        if raw is None:
            continue
        try:
            t = _parse_ts(raw)
        except ValueError:
            continue
        if best is None or t > best:
            best = t
    return best


def _window_cutoff(observations, window_days, now):
    """cutoff = anchor - window_days, where the anchor is `now` (if given and
    not wall-clock-dependent) else the NEWEST observation — the deterministic,
    idempotent anchor that makes a re-run byte-identical (AC4)."""
    base = _as_dt(now) if now is not None else newest_ts(observations)
    if base is None:
        return None
    return base - timedelta(days=window_days)


def _as_dt(x):
    if isinstance(x, datetime):
        return x.replace(tzinfo=None)
    if x is None:
        return None
    return _parse_ts(x)


def _contiguous_window_suffix(pts: list[dict], cutoff) -> list[dict]:
    """The in-window points of a sku PLUS a contiguous block of *older real*
    points rescued just below the in-window edge, stopping at the FIRST synthetic
    met.

    This is the synthetic-first eviction (#5 AC2): when the window must trim, a
    real point of equivalent age beats the synthetic it would otherwise evict, so
    we walk the out-of-window points newest-first, keeping reals and halting at the
    first old synthetic (which and everything older is then dropped). The result is
    always a contiguous SUFFIX of the sku's ascending series — so AC5's "no gaps /
    no broken/overlapping points / the boundary never cuts through a sku's needed
    points" holds.
    """
    inw = [p for p in pts if _obs_ts_key(p) >= cutoff]
    if not inw:
        return []
    oldest_inw = _obs_ts_key(inw[0])
    below = [p for p in pts if _obs_ts_key(p) < oldest_inw]
    rescued = []
    for p in reversed(below):              # walk out-of-window newest-first
        if _is_real(p):
            rescued.append(p)
        else:
            break                          # first old synthetic -> stop; it & older drop
    return rescued + inw


def apply_window(observations: list[dict],
                 window_days: "Optional[int]" = DEFAULT_WINDOW_DAYS,
                 now=None,
                 cutoff=None) -> list[dict]:
    """Keep only the most recent `window_days` of an observation list (#5 AC1).

    Per sku the series is reduced to a contiguous, windowed suffix:
      * in-window points (observed_at >= cutoff) are always kept;
      * if the sku has any synthetic point, the tail is extended down through
        adjacent *real* points, dropping the first old synthetic and everything
        older beneath it (synthetic-first eviction, real outranks — AC2);
      * a sku left with NO in-window point but WITH real points keeps its real
        evidence (AC2: "if it has any real points, keep those");
      * a sku with NO in-window point AND NO real point is dropped entirely
        (it is "discontinued" — surfaced via the sidecar, AC3).

    `cutoff` may be passed (else it is derived: `now` if given, else the NEWEST
    observation — the idempotent anchor, AC4). The output is deterministically
    ordered by the same key `dump_observations` uses, and `apply_window` is
    idempotent: re-applying it to an already-windowed list is a no-op (the newest
    point always survives, so nothing moves).
    """
    if not observations:
        return []
    if cutoff is None:
        cutoff = _window_cutoff(observations, window_days, now)
    if cutoff is None:
        return []
    bysku: dict = {}
    for o in observations:
        bysku.setdefault(str(o.get("sku")), []).append(o)
    kept: list[dict] = []
    for sku in sorted(bysku):
        pts = bysku[sku]
        pts.sort(key=_obs_ts_key)
        has_reals = any(_is_real(p) for p in pts)
        has_syn = any(not _is_real(p) for p in pts)
        inw = [p for p in pts if _obs_ts_key(p) >= cutoff]
        if inw:
            kept_pts = _contiguous_window_suffix(pts, cutoff) if has_syn else list(inw)
        elif has_reals:
            kept_pts = [p for p in pts if _is_real(p)]      # keep the real evidence
        else:
            continue                                         # discontinued -> drop (AC3)
        kept.extend(kept_pts)
    return sorted(kept, key=lambda o: (str(o.get("sku", "")),
                                       o.get("observed_at", ""),
                                       _syn_int(o)))


def resolve_window_days() -> int:
    """The effective window, resolved from the HISTORY_WINDOW_DAYS env var and
    falling back to the default. Non-positive / non-numeric -> the default."""
    raw = os.environ.get(ENV_WINDOW, "").strip()
    if not raw:
        return DEFAULT_WINDOW_DAYS
    try:
        n = int(raw)
        return n if n > 0 else DEFAULT_WINDOW_DAYS
    except ValueError:
        return DEFAULT_WINDOW_DAYS


def discontinued_skus(observations: list[dict],
                      window_days: "Optional[int]" = DEFAULT_WINDOW_DAYS,
                      now=None) -> set:
    """SKUs that are "discontinued" under the window (#5 AC3): their latest
    observation is older than the window (no in-window point) AND they carry no
    real point (only synthetic history). Only such a sku may be pruned outright;
    its last observation is still surfaced via the sidecar so it is never a
    dangling/orphan row. An in-window sku, or a sku with any real point, is kept.
    """
    if not observations:
        return set()
    cutoff = _window_cutoff(observations, window_days, now)
    if cutoff is None:
        return set()
    bysku: dict = {}
    for o in observations:
        bysku.setdefault(str(o.get("sku")), []).append(o)
    out: set = set()
    for sku, pts in bysku.items():
        has_inw = any(_obs_ts_key(p) >= cutoff for p in pts)
        has_reals = any(_is_real(p) for p in pts)
        if not has_inw and not has_reals:
            out.add(sku)
    return out


def _latest_record(observations: list[dict], sku: str) -> "Optional[dict]":
    """The sidecar record for a discontinued sku, built from its LATEST
    observation so the alert scanner / watchlist can still reference the sku."""
    pts = [o for o in observations if str(o.get("sku")) == sku]
    if not pts:
        return None
    latest = max(pts, key=_obs_ts_key)
    return {
        "sku": str(sku),
        "name": latest.get("name"),
        "tag": latest.get("tag"),
        "price": latest.get("price"),
        "currency": latest.get("currency", "TWD"),
        "source": latest.get("source", "costco"),
        "synthetic": _syn_int(latest),
        "last_observed_at": latest.get("observed_at"),
        "discontinued": True,
        "watched": False,
    }


def render_discontinued(observations: list[dict],
                        window_days: "Optional[int]" = DEFAULT_WINDOW_DAYS,
                        now=None,
                        watchlist_skus=None) -> list:
    """The full, deterministically ordered list of discontinued sidecar records
    for `observations` under `window_days`. A sku that is also in the watchlist
    is flagged `watched=True` — the #4 decoupling: it is FLAGGED, never deleted
    from watchlist.json by the retention path."""
    disc = discontinued_skus(observations, window_days=window_days, now=now)
    watched = {str(s) for s in (watchlist_skus or [])}
    out = []
    for sku in sorted(disc):
        rec = _latest_record(observations, sku)
        if rec is not None:
            rec["watched"] = sku in watched
            out.append(rec)
    return out


def flag_discontinued_watchlist(watchlist, discontinued) -> list:
    """Non-mutating report of watchlist entries whose sku is discontinued (#5 AC3,
    decoupling — #4). Returns the flagged entries; the watchlist list/file itself
    is NEVER modified or deleted. `discontinued` may be a set of skus or a list of
    sidecar records."""
    if isinstance(discontinued, (list, tuple)):
        disc = {str(r.get("sku")) if isinstance(r, dict) else str(r)
                for r in (discontinued or [])}
    else:
        disc = {str(s) for s in (discontinued or [])}
    out = []
    for e in watchlist or []:
        if not isinstance(e, dict):
            continue
        sku = e.get("sku")
        if sku is not None and str(sku) in disc:
            out.append({
                "sku": str(sku),
                "name": e.get("name"),
                "threshold": e.get("threshold"),
                "flag": "discontinued",
            })
    return out


def load_discontinued(path: str = DISCONTINUED_PATH) -> list:
    """Read the discontinued sidecar. [] when absent/corrupt — like
    load_observations, it never raises."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def dump_discontinued_records(records: list,
                              path: str = DISCONTINUED_PATH) -> int:
    """Write the discontinued sidecar deterministically (sort_keys + fixed indent)
    so a re-run that leaves the set unchanged produces a byte-identical file
    (AC4) — the same guarantee load/save gives the watchlist and the dedup state."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(records), f, ensure_ascii=False, indent=1, sort_keys=True)
    return len(records)


def prune_to_window(observations=None,
                    persist_path: str = PERSIST_PATH,
                    discontinued_path: str = DISCONTINUED_PATH,
                    window_days: "Optional[int]" = None,
                    now=None,
                    watchlist_skus=None,
                    watchlist=None) -> dict:
    """The refresh-path driver (#5 AC6): apply the rolling window to the SSOT and
    rewrite BOTH artifacts deterministically + idempotently:
      * `persist_path`       <- the windowed observations (AC1);
      * `discontinued_path`  <- the accumulated sidecar of evicted skus (AC3);
    a discontinued sku that is ALSO watched is flagged (AC3) but watchlist.json is
    NEVER written (the #4 decoupling).

    `window_days=None` resolves via `resolve_window_days()` (env / default).
    `now` is left as None so the window anchors on the NEWEST observation — the only
    thing that makes a re-run of THIS function on the already-pruned file byte-
    identical (AC4). `watchlist` (a watchlist list) is optional; its skus flag the
    sidecar. Returns a stats dict.
    """
    obs = load_observations(persist_path) if observations is None else observations
    if window_days is None:
        window_days = resolve_window_days()
    if watchlist_skus is None and watchlist is not None:
        from watchlist import skus as _wl_skus
        watchlist_skus = _wl_skus(watchlist)
    watch = {str(s) for s in (watchlist_skus or [])}

    disc = discontinued_skus(obs, window_days=window_days, now=now)
    windowed = apply_window(obs, window_days=window_days, now=now)

    # Rewrite the SSOT. Idempotent: when `obs` is already windowed, `apply_window`
    # is a no-op and `dump_observations` reproduces the exact bytes (AC4).
    dump_observations(windowed, persist_path, window_days=None, now=now)

    # The sidecar ACCUMULATES: keep every previously-known discontinued record,
    # add newly-discontinued skus, and drop any that reactivated (came back into
    # the windowed series). A re-run is therefore byte-identical for the file and
    # the sidecar (AC4).
    prev = {str(r.get("sku")): r for r in load_discontinued(discontinued_path)
            if isinstance(r, dict)}
    for sku in sorted(disc):
        if sku not in prev:
            rec = _latest_record(obs, sku)
            if rec is not None:
                rec["watched"] = sku in watch
                prev[sku] = rec
    survived = {str(o.get("sku")) for o in windowed}
    records = []
    for sku in sorted(prev):
        if sku in survived:
            continue                       # reactivated -> no longer orphaned
        r = dict(prev[sku])
        r["watched"] = sku in watch
        records.append(r)
    dump_discontinued_records(records, discontinued_path)

    flags = flag_discontinued_watchlist(watchlist, disc) if watchlist is not None \
        else flag_discontinued_watchlist([], disc)
    return {
        "before": len(obs),
        "after": len(windowed),
        "dropped": len(obs) - len(windowed),
        "window_days": window_days,
        "discontinued": sorted(disc),
        "watchlist_flags": flags,
        "records": records,
    }


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

