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
    _is_real,
    _load_rows,
    detect_new_real,
    format_report,
    main,
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


# ================== FIX [1]: unparseable observed_at is UNORDERABLE ==========
# A malformed observed_at must neither (a) fabricate a false landing nor (b) — if
# it wins the baseline's newest — silently mask every later real landing. It is
# DROPPED from the max/new computation and a WARNING is printed so nothing is
# silently swallowed. (The old (1, raw) key sorted a bad stamp ABOVE every
# parseable point — the exact defect this locks down.)

def test_unparseable_real_dropped_parseable_still_lands(capsys):
    """A malformed real (in BOTH baseline + cur) is ignored; a parseable real
    that is genuinely later than the parseable baseline max STILL lands."""
    prev = [
        _row("100", "not-a-timestamp"),              # malformed baseline point
        _row("200", "2026-11-10T00:00:00"),          # parseable baseline max
    ]
    cur = prev + [
        _row("300", "garbage-again"),                # malformed new point -> dropped
        _row("100", "2026-11-11T00:00:00"),          # genuinely NEW + parseable
    ]
    r = detect_new_real(prev, cur)
    assert r["landed"] is True
    assert r["new_count"] == 1                        # only the new parseable one
    assert r["new_last_observed_at"] == "2026-11-11T00:00:00"  # NOT a garbage max
    assert r["prev_last_observed_at"] == "2026-11-10T00:00:00"  # NOT "not-a-timestamp"
    # counts still span ALL reals (parseable or not); only the NEW/max is filtered
    assert r["prev_count"] == 2
    assert r["cur_count"] == 4
    # ...and the drop is NOT silent
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "UNPARSEABLE" in err


def test_unparseable_baseline_newest_does_not_mask_landing(capsys):
    """The exact 'mask later landings' defect: the baseline's newest real point is
    itself malformed. Under the old (1, raw) key it would sort above every
    parseable point and swallow this landing entirely — the guard must NOT."""
    prev = [
        _row("200", "2026-11-10T00:00:00"),
        _row("400", "not-a-timestamp"),               # newest baseline point is BAD
    ]
    cur = prev + [
        _row("300", "2026-11-11T00:00:00"),          # a genuine later landing
    ]
    r = detect_new_real(prev, cur)
    assert r["landed"] is True
    assert r["new_count"] == 1
    assert r["new_last_observed_at"] == "2026-11-11T00:00:00"
    assert r["prev_last_observed_at"] == "2026-11-10T00:00:00"  # max ignores the bad stamp
    assert "WARNING" in capsys.readouterr().err


def test_only_malformed_reals_never_land_or_take_max(capsys):
    """Malformed reals in BOTH baseline + cur, with NO parseable point at all: no
    landing, no fabricated max; the bad stamps never win the max or count as new,
    and the drop is warned (never silent)."""
    prev = [_row("100", "garbage-prev-1"), _row("100", "garbage-prev-2")]
    cur = prev + [_row("300", "garbage-cur")]
    r = detect_new_real(prev, cur)
    assert r["landed"] is False
    assert r["new_count"] == 0
    assert r["new_last_observed_at"] is None
    assert r["prev_last_observed_at"] is None
    # still counts the (parseable-or-not) reals for prev/cur
    assert r["prev_count"] == 2
    assert r["cur_count"] == 3
    assert "WARNING" in capsys.readouterr().err


# ================== FIX [6]: synthetic int() coercion + the tie boundary =======
def test_synthetic_zero_string_counts_but_truthy_excluded():
    """`synthetic` coercion: a string '0' tolerates as real, but 1 / True / any
    non-zero do NOT. (True is an int subclass == 1, so `int(v) == 0` would WRONGLY
    count it — the membership test below rejects truthy values.)"""
    assert _is_real(_row("a", "2026-11-11T00:00:00", synthetic="0")) is True
    assert _is_real({"source": "costco", "synthetic": "0"}) is True       # raw '0'
    assert _is_real(_row("b", "2026-11-11T00:00:00", synthetic=1)) is False
    assert _is_real({"source": "costco", "synthetic": 1}) is False
    assert _is_real(_row("c", "2026-11-11T00:00:00", synthetic=True)) is False
    assert _is_real({"source": "costco", "synthetic": True}) is False     # bool

    # and detection drops the truthy ones, counts the tolerable string '0'
    cur = [
        _row("100", "2026-11-11T00:00:00", synthetic=1),     # not real
        _row("200", "2026-11-11T00:00:00", synthetic=True),  # not real (bool)
        _row("300", "2026-11-11T00:00:00", synthetic="0"),   # real (string '0')
    ]
    r = detect_new_real([], cur)   # no baseline -> every REAL point is new
    assert r["landed"] is True
    assert r["new_count"] == 1
    assert r["cur_count"] == 1
    assert r["new_last_observed_at"] == "2026-11-11T00:00:00"


def test_two_new_reals_tying_the_same_new_observed_at_both_count():
    """The both-greater TIE the reviewer flagged: two NEW real rows sharing the
    SAME observed_at (both strictly > the baseline) must BOTH count — the existing
    tests only covered the == (not-newer) boundary."""
    prev = [_row("100", "2026-11-10T00:00:00")]              # baseline newest
    cur = [
        _row("100", "2026-11-10T00:00:00"),                  # == baseline -> NOT new
        _row("200", "2026-11-11T00:00:00"),                  # NEW (ties 300)
        _row("201", "2026-11-11T00:00:00"),                  # NEW, SAME ts -> also counts
    ]
    r = detect_new_real(prev, cur)
    assert r["landed"] is True
    assert r["new_count"] == 2
    assert r["new_last_observed_at"] == "2026-11-11T00:00:00"
    assert r["prev_last_observed_at"] == "2026-11-10T00:00:00"


# ================== FIX [3]: main() / fail-mode / _load_rows offline =========
def _no_landing_pair(tmp_path):
    """A baseline that carries a real point, and a current identical to it (nothing
    newer) -> a genuine no-landing run (not a fabricated one)."""
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    data = json.dumps([_row("100", "2026-11-10T00:00:00")])
    base.write_text(data)
    cur.write_text(data)
    return base, cur


def test_main_no_landing_default_warns_not_fails(tmp_path, monkeypatch):
    """(a) default args, no landing => main returns 0 (WARN, not FAIL)."""
    monkeypatch.delenv("STALL_GUARD_FAIL", raising=False)
    base, cur = _no_landing_pair(tmp_path)
    assert main(["--prev", str(base), "--cur", str(cur)]) == 0


def test_main_fail_flag_hard_fails_on_no_landing(tmp_path, monkeypatch):
    """(b) the --fail flag turns a no-landing into a hard fail (returns 1)."""
    monkeypatch.delenv("STALL_GUARD_FAIL", raising=False)
    base, cur = _no_landing_pair(tmp_path)
    assert main(["--prev", str(base), "--cur", str(cur), "--fail"]) == 1
    # ...and with a landing the same flag stays happy (0)
    landed = tmp_path / "landed.json"
    landed.write_text(json.dumps([
        _row("300", "2026-11-12T00:00:00"),
    ]))
    assert main(["--prev", str(base), "--cur", str(landed), "--fail"]) == 0


@pytest.mark.parametrize("val", ["1", "true", "True", "yes"])
def test_main_env_fail_hard_fails_on_no_landing(tmp_path, monkeypatch, val):
    """(c) a truthy STALL_GUARD_FAIL env var turns a no-landing into a fail."""
    base, cur = _no_landing_pair(tmp_path)
    monkeypatch.setenv("STALL_GUARD_FAIL", val)
    assert main(["--prev", str(base), "--cur", str(cur)]) == 1


@pytest.mark.parametrize("val", ["", "0", "false", "no", "False"])
def test_main_env_nonfail_stays_green(tmp_path, monkeypatch, val):
    """A non-truthy STALL_GUARD_FAIL must NOT hard-fail (warn-not-fail stays green)."""
    base, cur = _no_landing_pair(tmp_path)
    monkeypatch.setenv("STALL_GUARD_FAIL", val)
    assert main(["--prev", str(base), "--cur", str(cur)]) == 0


def test_load_rows_real_path_empty_file_returns_empty_list(tmp_path):
    """(d) a real path whose file is empty => [] WITHOUT crashing; whitespace-only
    collapses to [] too. No network, no .db, no crawl."""
    empty = tmp_path / "empty.json"
    empty.write_text("")
    assert _load_rows(str(empty)) == []

    ws = tmp_path / "ws.json"
    ws.write_text("   \n\t  ")
    assert _load_rows(str(ws)) == []
