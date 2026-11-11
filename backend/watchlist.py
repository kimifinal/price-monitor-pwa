"""watchlist.py — the 個人化 (per-item) alert gate for #4.

A git-diffable JSON SSOT (`watchlist.json`) lists the skus a user *actually* wants
alerts for, each with an optional per-item `threshold` — a target price and/or a
minimum drop-from-high %. This is a *separate concern* from the time-series
(`history_data.json`): toggling the watchlist (add / remove / edit) must NEVER
rewrite the series. That decoupling is what lets a user personalize their alerts
without churning the one observation a day keeps accumulating — the time-series
stays append-only, the watchlist is a small, independent file.

The verdict itself stays sourced from ONE place — `models.price_verdict` (the SSOT,
reused by `alerts.scan`). The watchlist + threshold is only the GATE that decides
which of those verdicts are allowed to fire:
  * alert only for skus that are IN the watchlist AND meet their OWN threshold;
  * an unwatched sku never alerts, even at an all-time low;
  * an empty watchlist => no alerts (the safe, silent default).

The per-item threshold rule lives here and is mirrored on the frontend by
`frontend/src/lib/watchlist.js`: a target price reuses `models.should_alert`
(never a second price rule), and a min-drop compares against the sku's
`drop_pct_from_high` — the exact metric the verdict SSOT reads.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from models import should_alert   # the target-price rule — reused, never re-implemented

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "watchlist.json")

# An empty watchlist is the safe, silent default (#4 AC): nothing fires.
EMPTY_WATCHLIST: list = []


def load(path: str = WATCHLIST_PATH) -> list:
    """Read the watchlist SSOT.

    Returns a list (possibly empty). `[]` when the file is absent or malformed —
    it never raises, so a corrupt or missing watchlist can't crash the pipeline
    (offline-safe, like `alerts.load_state`).
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return data


def save(entries: list, path: str = WATCHLIST_PATH) -> int:
    """Persist the watchlist deterministically so the git diff is reviewable —
    the same guarantee `alerts.save_state` gives its dedup state. Field order is
    stable (`sort_keys=True`) and the indent fixed, so re-saving the same entries
    produces a byte-identical file (idempotent, no churn). Returns entry count.

    A watchlist entry is `{sku, name?, threshold?}` where `threshold` is a dict of
    `{"target"?, "min_drop_pct"?}`. Non-dict junk entries are dropped so a bad
    line can't poison the SSOT.
    """
    clean = [e for e in (entries or []) if isinstance(e, dict) and e.get("sku") is not None]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=1, sort_keys=True)
    return len(clean)


def skus(watchlist: Optional[list]) -> list:
    """Distinct skus in the watchlist (stable order, as strings). Skus compare as
    strings so '149699' and 149699 gate the same item; a sku-less entry is a no-op
    and skipped."""
    out: list = []
    seen: set = set()
    for e in watchlist or []:
        if not isinstance(e, dict) or e.get("sku") is None:
            continue
        s = str(e["sku"])
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def find_entry(m: dict, watchlist: Optional[list]) -> Optional[dict]:
    """The watchlist entry whose sku matches metrics `m`, or None when `m` is not
    watched. Skus compare as strings (`'149699'` == `149699`)."""
    if not watchlist or not m:
        return None
    sku = m.get("sku")
    if sku is None:
        return None
    sku = str(sku)
    for e in watchlist:
        if isinstance(e, dict) and e.get("sku") is not None and str(e["sku"]) == sku:
            return e
    return None


def threshold_met(m: dict, entry: Optional[dict]) -> bool:
    """Does item `m` satisfy its own per-item threshold?

      * a `target`       => reuse `models.should_alert(current, target)` — the ONE
                            price rule, never a second (price <= target);
      * a `min_drop_pct`  => `drop_pct_from_high >= min_drop_pct` — the sku's OWN
                            drop from its all-time high (the metric verdict reads);
      * both present      => BOTH must hold (a stricter gate);
      * neither present   => the entry imposes no numeric gate — any firing verdict
                            counts.

    A missing `current` (for a target) or `drop_pct_from_high` (for a min-drop) is
    treated as NOT met for that field, so a threshold can't fire on missing data.
    """
    if not isinstance(entry, dict):
        return True
    th = entry.get("threshold")
    if not isinstance(th, dict):
        th = {}
    target = th.get("target")
    if target is not None:
        price = m.get("current")
        if price is None:
            return False
        if not should_alert(price, target):            # the SSOT price rule, reused
            return False
    min_drop = th.get("min_drop_pct")
    if min_drop is not None:
        drop = m.get("drop_pct_from_high")
        if drop is None:
            return False
        if drop < min_drop:
            return False
    return True


def gate(m: dict, watchlist: Optional[list]) -> bool:
    """The full #4 gate: item `m` may alert only if it is IN the watchlist AND its
    threshold is met.

      * `watchlist is None`  => gate disabled (legacy verdict-only behaviour);
      * `watchlist == []`    => nothing passes (the silent, default-silent AC);
      * else                => watchlisted skus whose threshold is met.
    """
    if watchlist is None:
        return True
    entry = find_entry(m, watchlist)
    if entry is None:
        return False
    return threshold_met(m, entry)


if __name__ == "__main__":
    wl = load()
    print(f"watchlist: {len(wl)} entr(ies) tracking {len(skus(wl))} sku(s)")
    for e in skus(wl):
        print(f"  - {e}")
