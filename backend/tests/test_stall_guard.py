"""Offline tests for the stall-guard (issue #12).

The guard proves that a scheduled refresh actually *landed* a new real costco
point into the append-only history SSOT. It is pure + fixture-driven — NO
network, NO .db, NO real crawl. prev/cur are in-memory JSON arrays mirroring
``backend/history_data.json`` rows:

    {sku, name, tag, price, currency, observed_at, source, synthetic}

A "real" point == ``source == "costco"`` AND ``synthetic == 0``. A new real
point is one whose ``observed_at`` is strictly later than the pre-refresh
baseline's newest real ``observed_at`` (by TIME, never by array order).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stall_guard import (
    detect_new_real,
    format_report,
    real_rows,
    write_state_if_landed,
    GUARD_VERSION,
    STATE_SOURCE,
)


# ---- helpers to build history rows with as little noise as possible --------
def _row(sku, observed_at, *, source="costco", synthetic=0, price=100.0):
    return {
        "sku": sku,
        "name": f"item {sku}",
        "tag": "3C",
        "price": price,
        "currency": "TWD",
        "observed_at": observed_at,
        "source": source,
        "synthetic": synthetic,
    }


def _backfill(sku, observed_at, price=110.0):
    # human backfill point — must NEVER count as a real landing
    return _row(sku, observed_at, source="backfill", synthetic=1, price=price)


# ----------------------- AC1: a landing -----------------------------------
def test_landing_detects_new_real_point_by_time_not_array_order():
    """A real point with a newer observed_at than the baseline is 'new',
    regardless of where it sits in the array. new_last is the MAX BY TIME."""
    prev = [
        _row("100", "2026-11-10T00:00:00"),   # baseline newest real = 11-10
        _row("200", "2026-11-09T00:00:00"),
    ]
    # cur array is deliberately NOT in time order, and the newest (11-13) sits
    # in the MIDDLE. Two backfill rows must be ignored.
    cur = [
        _row("300", "2026-11-13T00:00:00"),   # NEW  (mid-array, the max by time)
        _backfill("300", "2026-11-13T08:00:00"),
        _row("100", "2026-11-11T00:00:00"),   # NEW
        _row("100", "2026-11-12T00:00:00"),   # NEW
        _backfill("200", "2026-11-10T08:00:00"),
        _row("200", "2026-11-10T00:00:00"),   # not new (== baseline newest)
    ]
    r = detect_new_real(prev, cur)
    assert r["landed"] is True
    assert r["new_count"] == 3
    # must be the time-max even though it was mid-array
    assert r["new_last_observed_at"] == "2026-11-13T00:00:00"
    assert r["prev_last_observed_at"] == "2026-11-10T00:00:00"
    # counts over REAL rows only (backfill/synthetic excluded)
    assert r["prev_count"] == 2
    assert r["cur_count"] == 4   # 11-13, 11-11, 11-12, 11-10(dup) — all costco/0


# ----------------------- AC2a: no new real --------------------------------
def test_no_new_real_point_backfill_does_not_count():
    """A run that appends only backfill/synthetic rows (and a real point that is
    not newer than the baseline) is NOT a landing."""
    prev = [
        _row("100", "2026-11-12T00:00:00"),
        _row("200", "2026-11-12T00:00:00"),
    ]
    cur = prev + [
        _backfill("100", "2026-11-13T08:00:00"),     # new in time but synthetic
        _backfill("201", "2026-11-13T09:00:00"),
        _row("100", "2026-11-11T00:00:00"),          # real but OLDER than baseline
        _row("100", "2026-11-12T00:00:00"),          # real, == baseline (not >)
        _row("300", "2026-11-12T00:00:00"),          # real, == baseline
    ]
    r = detect_new_real(prev, cur)
    assert r["landed"] is False
    assert r["new_count"] == 0
    assert r["new_last_observed_at"] is None
    assert r["prev_last_observed_at"] == "2026-11-12T00:00:00"
    assert r["prev_count"] == 2
    # cur has 5 real (prev 2 + 3 new-duplicate/older reals) — still counted; only the
    # "new/strictly-later" subset is what a landing means.
    assert r["cur_count"] == 5


def test_no_real_rows_at_all():
    """Empty baseline + empty/only-synthetic current => no landing, all None."""
    r = detect_new_real([], [_backfill("x", "2026-11-13T00:00:00")])
    assert r == {
        "landed": False,
        "new_count": 0,
        "new_last_observed_at": None,
        "prev_last_observed_at": None,
        "prev_count": 0,
        "cur_count": 0,
    }


def test_no_baseline_treats_all_real_as_new():
    """With no real baseline, every real costco point in cur is a new landing."""
    cur = [
        _row("300", "2026-11-13T00:00:00"),
        _row("100", "2026-11-05T00:00:00"),
        _backfill("100", "2026-11-05T08:00:00"),
    ]
    r = detect_new_real([], cur)
    assert r["landed"] is True
    assert r["new_count"] == 2
    assert r["new_last_observed_at"] == "2026-11-13T00:00:00"
    assert r["prev_count"] == 0
    assert r["cur_count"] == 2


# ----------------------- (iii): reordering is time-based -------------------
def test_reordering_the_array_does_not_change_the_verdict():
    import random
    reals = [
        _row("300", "2026-11-14T00:00:00"),
        _row("100", "2026-11-15T00:00:00"),
        _row("100", "2026-11-13T00:00:00"),
        _row("200", "2026-11-16T00:00:00"),
    ]
    prev = [_row("100", "2026-11-12T00:00:00")]
    base = detect_new_real(prev, reals)
    for seed in (0, 1, 2, 3, 7):
        shuffled = list(reals)
        random.Random(seed).shuffle(shuffled)
        r = detect_new_real(prev, shuffled)
        assert r["landed"] == base["landed"]
        assert r["new_count"] == base["new_count"]
        assert r["new_last_observed_at"] == base["new_last_observed_at"]
    # and the verdict matches the time-max, not the array-last
    assert base["new_last_observed_at"] == "2026-11-16T00:00:00"
    assert base["new_count"] == 4


# ----------------------- AC3/AC4: state SSOT written only on landing -------
def test_refresh_state_written_only_on_landing(tmp_path):
    prev = [_row("100", "2026-11-10T00:00:00")]
    cur = [prev[0], _row("100", "2026-11-12T00:00:00")]
    state = tmp_path / "refresh_state.json"

    # Not-landed run must NOT create or touch the SSOT (so "since when" stays
    # visible). A pre-existing file must be left byte-for-byte intact.
    state.write_text(json.dumps({"bootstrap": True}))
    r0 = detect_new_real(prev, prev)
    assert write_state_if_landed(r0, str(state), cur, now="2026-11-12T04:00:00Z") is False
    assert json.loads(state.read_text()) == {"bootstrap": True}   # untouched

    # A landing DOES write it, and only then.
    r1 = detect_new_real(prev, cur)
    assert write_state_if_landed(r1, str(state), cur, now="2026-11-12T04:00:00Z") is True
    doc = json.loads(state.read_text())
    assert doc["updated_at"] == "2026-11-12T04:00:00Z"
    assert doc["last_real_observed_at"] == "2026-11-12T00:00:00"  # latest real
    assert doc["last_real_count"] == r1["cur_count"] == 2
    assert doc["new_real_this_run"] == r1["new_count"] == 1
    assert doc["guard_version"] == GUARD_VERSION == "1"
    assert doc["source"] == STATE_SOURCE == "backend/stall_guard.py issue #12"


def test_refresh_state_schema_shape(tmp_path):
    """refresh_state.json is valid JSON with exactly the 6 schema keys + types."""
    prev = [_row("100", "2026-11-10T00:00:00")]
    cur = [prev[0], _row("100", "2026-11-12T00:00:00")]
    state = tmp_path / "refresh_state.json"
    r = detect_new_real(prev, cur)
    write_state_if_landed(r, str(state), cur, now="2026-11-12T04:00:00Z")

    raw = state.read_text()
    doc = json.loads(raw)            # valid JSON
    assert set(doc) == {
        "updated_at",
        "last_real_observed_at",
        "last_real_count",
        "new_real_this_run",
        "guard_version",
        "source",
    }
    assert isinstance(doc["updated_at"], str)
    assert isinstance(doc["last_real_observed_at"], str)
    assert isinstance(doc["last_real_count"], int)
    assert isinstance(doc["new_real_this_run"], int)
    assert doc["guard_version"] == "1"
    assert doc["source"] == "backend/stall_guard.py issue #12"


# ----------------------- (v): format_report both branches ------------------
def test_format_report_landed():
    r = {
        "landed": True,
        "new_count": 3,
        "new_last_observed_at": "2026-11-13T00:00:00",
        "prev_last_observed_at": "2026-11-10T00:00:00",
        "prev_count": 2,
        "cur_count": 4,
    }
    out = format_report(r, "2026-11-10T00:00:00")
    assert out == (
        "✅ [stall-guard] 本次落地 3 個真實 costco 點;"
        "last_real=2026-11-13T00:00:00;SSOT 已更新"
    )


def test_format_report_not_landed():
    r = {
        "landed": False,
        "new_count": 0,
        "new_last_observed_at": None,
        "prev_last_observed_at": "2026-11-12T00:00:00",
        "prev_count": 2,
        "cur_count": 2,
    }
    out = format_report(r, "2026-11-12T00:00:00")
    assert out == (
        "⚠️  [stall-guard] 本次無新真實 costco 點 "
        "—— 抓取可能靜默失敗/停滯;歷史自 2026-11-12T00:00:00 以來未變"
    )


def test_format_report_not_landed_no_baseline():
    """No real baseline at all: the 'since' renders as 'never'."""
    r = {
        "landed": False,
        "new_count": 0,
        "new_last_observed_at": None,
        "prev_last_observed_at": None,
        "prev_count": 0,
        "cur_count": 0,
    }
    out = format_report(r, None)
    assert "歷史自 never 以來未變" in out
    assert "⚠️  [stall-guard]" in out


# ----------------------- real-data sanity (the live SSOT) ------------------
def test_real_history_has_real_points():
    """The shipped history really does carry real costco points the guard counts.

    Reads the real artifact by path (no crawl, no db) so the guard is proven
    against the live SSOT, not just against fixtures."""
    art = Path(__file__).resolve().parent.parent / "history_data.json"
    rows = json.loads(art.read_text(encoding="utf-8"))
    reals = real_rows(rows)
    assert len(reals) > 0
    latest = max(r["observed_at"] for r in reals)
    r = detect_new_real(rows, [_row("300", "2099-01-01T00:00:00")])
    assert r["landed"] is True
    assert r["new_count"] == 1
    assert r["new_last_observed_at"] == "2099-01-01T00:00:00"
    # and a baseline already at the live max is NOT a landing
    same = detect_new_real(rows, rows)
    assert same["landed"] is False
    assert same["new_count"] == 0
    assert len(reals) == same["prev_count"]
    assert latest.startswith("2026-")  # shape sanity
