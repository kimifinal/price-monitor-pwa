"""Offline tests for the price-history store (SQLite time series).

All use an in-memory DB or an explicit tmp path — no file, no network, no real
time. Determinism is a core guarantee (seed_from_snapshot is seeded per sku).
"""
from datetime import datetime

import pytest

from importlib import reload

import history

# Fresh module state so a re-imported schema can't mask a stale connection.
reload(history)


@pytest.fixture()
def db(tmp_path):
    """A fresh, isolated on-disk history DB per test."""
    return history.connect(str(tmp_path / "h.db"))


# ----------------------- record / dedup -----------------------
def test_record_appends_and_dedups(db):
    items = [{"sku": "100", "name": "A", "price": 50.0, "tag": "3C"}]
    assert history.record(items, ts="2026-01-01T00:00:00", conn=db) == 1
    # same sku/price/source/ts -> 0 new rows (idempotent within a scrape)
    assert history.record(items, ts="2026-01-01T00:00:00", conn=db) == 0
    # a new timestamp with the same price is still a new point
    assert history.record(items, ts="2026-01-02T00:00:00", conn=db) == 1
    assert len(history.series("100", conn=db)) == 2


def test_record_skips_missing_price_or_sku(db):
    n = history.record(
        [
            {"sku": None, "name": "x", "price": 10.0},
            {"sku": "200", "name": "y", "price": None},
            {"sku": "300", "name": "z"},
            {"sku": "400", "name": "ok", "price": 42.0},
        ],
        ts="2026-01-01T00:00:00", conn=db,
    )
    assert n == 1
    assert history.series("400", conn=db) == [("2026-01-01T00:00:00", 42.0, "costco")]


# ----------------------- series / metrics -----------------------
def test_metrics_endpoints(db):
    items = [{"sku": "77", "name": "Widget", "price": p, "tag": "家電"}
             for p in (100.0, 120.0, 80.0)]
    history.record([items[0]], ts="2026-01-01T00:00:00", conn=db)
    history.record([items[1]], ts="2026-01-02T00:00:00", conn=db)
    history.record([items[2]], ts="2026-01-03T00:00:00", conn=db)
    m = history.metrics("77", conn=db)
    assert m["high"] == 120.0
    assert m["low"] == 80.0
    assert m["current"] == 80.0
    assert m["at_all_time_low"] is True
    assert m["points"] == 3
    assert m["drop_pct_from_high"] == pytest.approx(33.3, rel=1e-1)


def test_metrics_unknown_sku(db):
    m = history.metrics("does-not-exist", conn=db)
    assert m == {"sku": "does-not-exist", "points": 0}


# ----------------------- deterministic seed -----------------------
def test_seed_is_deterministic(tmp_path):
    a = history.connect(str(tmp_path / "a.db"))
    b = history.connect(str(tmp_path / "b.db"))
    items = [{"sku": "999", "name": "Gadget", "price": 300.0, "tag": "3C"}]
    now = datetime(2026, 6, 1)
    history.seed_from_snapshot(items, days=14, now=now, conn=a)
    history.seed_from_snapshot(items, days=14, now=now, conn=b)
    sa = history.series("999", conn=a)
    sb = history.series("999", conn=b)
    assert sa == sb                       # identical across two DBs
    assert len(sa) == 14                  # 14 daily points
    assert sa[-1][1] == 300.0            # ends exactly at the current price


def test_seed_backfill_makes_current_near_low(db):
    items = [{"sku": "11", "name": "Cool", "price": 100.0, "tag": "家電"}]
    history.seed_from_snapshot(items, days=14, now=datetime(2026, 6, 1), conn=db)
    m = history.metrics("11", conn=db)
    assert m["points"] == 14
    assert m["drop_pct_from_high"] > 0    # it fell from its backfilled high
    assert m["at_all_time_low"] is True   # the final point is the series floor


def test_seed_is_idempotent(db):
    items = [{"sku": "22", "name": "x", "price": 50.0, "tag": "3C"}]
    now = datetime(2026, 6, 1)
    n1 = history.seed_from_snapshot(items, now=now, conn=db)
    n2 = history.seed_from_snapshot(items, now=now, conn=db)
    assert n1 > 0
    assert n2 == 0                         # re-seeding the same window adds nothing
