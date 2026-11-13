#!/usr/bin/env python3
"""Stall-guard (issue #12) — prove a scheduled refresh *really landed* a point.

The daily crawl has a blind spot: `cron '0 4 * * *'` in refresh-costco.yml has NO
check that it actually appends a NEW real costco observation to the history SSOT
(``backend/history_data.json``). If the crawl fails *silently*, the price series
stalls and nobody finds out — exactly the "not silent" gap that #15 (observability)
and #16 (liveness gate) set out to close. This module closes it for the *data*
half: after a refresh it asserts, in a way that is both **self-proving in the CI
log** and **queryable on disk**, that a real costco point landed this run, and it
leaves a "last successful refresh" SSOT.

A "real" point (the only thing that counts) is a history row with
``source == "costco"`` AND ``synthetic == 0``. A ``backfill`` /
``synthetic == 1`` row is a *human backpoint* and must NEVER count as a landing.
A point is "new" when its ``observed_at`` is strictly later than the PRE-refresh
baseline's newest real ``observed_at`` — by TIME, never by array order.

Core is PURE (no I/O, no network, no .db) so the whole thing is unit-testable with
fixtures. Only the CLI writer touches the filesystem.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Optional

GUARD_VERSION = "1"
STATE_SOURCE = "backend/stall_guard.py issue #12"

# refresh_state.json schema — the human/CI queryable "last successful refresh".
STATE_KEYS = (
    "updated_at",
    "last_real_observed_at",
    "last_real_count",
    "new_real_this_run",
    "guard_version",
    "source",
)


# --------------------------------------------------------------------------
# pure detection
# --------------------------------------------------------------------------
def _syn_is_zero(v) -> bool:
    """True iff a ``synthetic`` flag *normalizes* to 0 (a genuine observation).

    Tolerates a string '0' (some JSON serializers stringify ints, so a stray '0'
    must STILL count as a real point) but NEVER a truthy value: 1, True, or any
    other non-zero are backfill/synthetic and must NOT count. ``bool`` is an
    ``int`` subclass (``int(True) == 1``), so the naive ``int(v) == 0`` would
    wrongly treat ``True`` as a landing and a non-zero bool would slip through;
    the exact-membership test below rejects it.
    """
    return v in (0, "0")


def _is_real(row) -> bool:
    """A landing counts ONLY a genuine scraped observation, not a backfill.

    ``synthetic`` is normalized via :func:`_syn_is_zero`: a string '0' counts,
    while 1 / True / any other non-zero must never masquerade as a real costco
    point (a bool True, an int subclass == 1, would otherwise count as real).
    """
    return (isinstance(row, dict)
            and row.get("source") == "costco"
            and _syn_is_zero(row.get("synthetic")))


def real_rows(rows) -> list:
    """The real costco points among a history array (backfill/synthetic dropped)."""
    return [r for r in (rows or []) if _is_real(r)]


def _ts_dt(observed_at):
    """Parse an ISO-8601 ``observed_at`` to a ``datetime`` — or ``None`` if bad.

    An UNPARSEABLE timestamp is UNORDERABLE: the old ``(1, raw)`` fallback sorted
    it ABOVE every parseable ``(0, dt)`` row, so a single malformed real could
    either *fabricate* a landing or, worse, win the baseline's "newest" and then
    *silently mask* every later landing — defeating the guard. Callers therefore
    DROPP it (never rank it) and warn loudly so the drop is never silent.
    """
    try:
        return datetime.datetime.fromisoformat(str(observed_at))
    except (ValueError, TypeError):
        return None


def _warn_dropped(dropped: list) -> None:
    """Loud, non-silent notice for each UNIQUE real point dropped because its
    observed_at is UNPARSEABLE — so a swallowed landing is visible in the CI log.

    Dedup to one WARNING per (source, sku, observed_at) so a malformed point
    present in BOTH baseline and worktree warns once, not twice.
    """
    seen = set()
    for r in dropped:
        key = (str(r.get("source")), r.get("sku"), str(r.get("observed_at")))
        if key in seen:
            continue
        seen.add(key)
        sys.stderr.write(
            f"WARNING: [stall-guard] real point observed_at={r.get('observed_at')!r} "
            f"(source={r.get('source')!r}/sku={r.get('sku')!r}) has an UNPARSEABLE "
            f"observed_at — excluded from the landing/max computation (not counted)\n"
        )


def _latest_observed(real: list) -> Optional[str]:
    """The newest ``observed_at`` (a string) among real rows, by TIME not order.

    UNORDERABLE (unparseable) reals are skipped — a bad stamp may never win the
    max.
    """
    best = None
    best_dt = None
    for r in real:
        oa = r.get("observed_at")
        dt = _ts_dt(oa)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best = oa
    return best


def detect_new_real(prev_rows, cur_rows) -> dict:
    """Assert a refresh *landed* a real costco point.

    ``prev_rows`` is the pre-refresh baseline (the committed history this run
    started with); ``cur_rows`` is the post-refresh worktree history. A "new real
    point" is a real point in ``cur`` whose ``observed_at`` is strictly later than
    the baseline's newest *orderable* real ``observed_at`` — a pure TIME
    comparison, so the order the arrays happen to be written in is irrelevant.

    A real point with an UNPARSEABLE observed_at is UNORDERABLE: it must neither
    become the max nor count as new. It is DROPPED from BOTH the baseline and the
    new-landing set, and a WARNING is printed so a swallowed real point is never
    silent (the two failure modes a bad stamp defeats: a *fabricated* landing, and
    a baseline that silently *swallows every later* landing).

    Returns a result dict with: ``landed`` (new_count > 0), ``new_count``,
    ``new_last_observed_at`` (newest NEW point, by time), ``prev_last_observed_at``,
    ``prev_count`` / ``cur_count`` (counts over ALL real points, parseable or not).
    """
    prev_real = real_rows(prev_rows)
    cur_real = real_rows(cur_rows)

    # Drop UNORDERABLE (unparseable observed_at) reals from BASELINE and the NEW
    # set, warning about each unique drop so nothing is swallowed silently.
    prev_order = [r for r in prev_real if _ts_dt(r.get("observed_at")) is not None]
    cur_order = [r for r in cur_real if _ts_dt(r.get("observed_at")) is not None]
    _warn_dropped(
        [r for r in prev_real if _ts_dt(r.get("observed_at")) is None]
        + [r for r in cur_real if _ts_dt(r.get("observed_at")) is None]
    )

    prev_last = _latest_observed(prev_order)
    prev_dt = _ts_dt(prev_last)  # None when there is no orderable baseline

    new_count = 0
    new_last: Optional[str] = None
    new_last_dt = None
    for r in cur_order:
        oa = r.get("observed_at")
        dt = _ts_dt(oa)  # parseable by construction (cur_order dropped the bad rows)
        # No orderable baseline => every orderable real counts as new. Otherwise
        # only a point STRICTLY LATER than the baseline's newest qualifies. Ties
        # (two NEW points sharing the SAME observed_at, both > the baseline) count
        # their full multiplicity — each is a genuine landing.
        if prev_dt is None or dt > prev_dt:
            new_count += 1
            if new_last_dt is None or dt > new_last_dt:
                new_last_dt = dt
                new_last = oa

    return {
        "landed": new_count > 0,
        "new_count": new_count,
        "new_last_observed_at": new_last,
        "prev_last_observed_at": prev_last,
        "prev_count": len(prev_real),
        "cur_count": len(cur_real),
    }


def format_report(result, prev_ts) -> str:
    """One human-readable line, loud enough to self-prove in the CI log.

    ``prev_ts`` is the baseline's newest real ``observed_at`` (or None), used in the
    not-landed branch so "how long has it been stalled" is visible at a glance.
    """
    if result.get("landed"):
        n = result.get("new_count", 0)
        ts = result.get("new_last_observed_at")
        return (f"✅ [stall-guard] 本次落地 {n} 個真實 costco 點;"
                f"last_real={ts};SSOT 已更新")
    since = prev_ts if prev_ts else "never"
    return ("⚠️  [stall-guard] 本次無新真實 costco 點 "
            f"—— 抓取可能靜默失敗/停滯;歷史自 {since} 以來未變")


# --------------------------------------------------------------------------
# refresh_state.json — the one-write / one-read "last successful refresh" SSOT
# --------------------------------------------------------------------------
def build_state(result, cur_rows, updated_at) -> dict:
    """The exact 6-key refresh_state dict (see the §4 schema in the spec)."""
    real = real_rows(cur_rows)
    return {
        "updated_at": updated_at,
        "last_real_observed_at": _latest_observed(real),
        "last_real_count": len(real),
        "new_real_this_run": result.get("new_count", 0),
        "guard_version": GUARD_VERSION,
        "source": STATE_SOURCE,
    }


def write_state_if_landed(result, state_path, cur_rows,
                          now: Optional[str] = None) -> bool:
    """Write refresh_state.json **only when a landing happened**.

    On a no-landing run it returns False and touches nothing — so ``updated_at``
    stays pinned to the last *successful* landing and "stalled since when" stays
    visible. Returns True (and writes the file) only when ``result['landed']``.
    ``now`` overrides the ``updated_at`` stamp (determinism in tests/CI).
    """
    if not result.get("landed"):
        return False
    stamp = now if now is not None else \
        datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = build_state(result, cur_rows, stamp)
    Path(state_path).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


# --------------------------------------------------------------------------
# CLI wiring (the only place that touches the filesystem)
# --------------------------------------------------------------------------
def _load_rows(path: str) -> list:
    """Load a history JSON array from ``path`` (or [''] when - means stdin)."""
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    raw = raw.strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--prev", required=True,
                   help="pre-refresh baseline history JSON (path; '-' = stdin)")
    p.add_argument("--cur", required=True,
                   help="post-refresh worktree history JSON path")
    p.add_argument("--state", default=None,
                   help="refresh_state.json path to (re)write on a landing")
    p.add_argument("--fail", action="store_true",
                   help="hard-fail (exit 1) when no real point landed "
                        "(default: WARN not-fail — a legitimately empty day stays green)")
    p.add_argument("--now", default=None,
                   help="override updated_at ISO timestamp (tests / determinism)")
    args = p.parse_args(argv)

    prev_rows = _load_rows(args.prev)
    cur_rows = _load_rows(args.cur)
    result = detect_new_real(prev_rows, cur_rows)

    # (d) print the [stall-guard] line LOUD: the CI log self-proves landed vs not.
    line = format_report(result, result["prev_last_observed_at"])
    print(line)

    # (e) on a landing, refresh_state.json rides out as the "last success" SSOT.
    wrote = bool(args.state) and write_state_if_landed(result, args.state, cur_rows, args.now)

    # WARN-not-fail by default — "not silent" is satisfied by the loud/recorded
    # warning above, NOT by RED-ing the daily cron for an honestly empty day.
    fail_mode = args.fail or os.environ.get("STALL_GUARD_FAIL", "").strip() in ("1", "true", "True", "yes")
    if result["landed"]:
        return 0
    if fail_mode:
        sys.stderr.write(
            f"::error::[stall-guard] no new real costco point this run "
            f"({result['new_count']} new); hard-failing per --fail/STALL_GUARD_FAIL\n")
        return 1
    sys.stderr.write(
        f"WARNING: [stall-guard] no new real costco point this run "
        f"(warn-not-fail mode; the [stall-guard] line above is the record)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
