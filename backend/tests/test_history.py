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

# A small fixed basket reused by the JSON-persistence tests (skus with prices,
# plus one "3C"/one "家電" so the tag field is exercised).
ITEMS = [
    {"sku": "139339", "name": "PQI 氮化鎵 35W", "price": 959.0, "tag": "3C"},
    {"sku": "143371", "name": "Soodatek 氮化鎵 65W", "price": 825.0, "tag": "3C"},
    {"sku": "3062725", "name": "BOSE Solo Soundbar", "price": 8149.0, "tag": "家電"},
    {"sku": "153519", "name": "Panasonic 4K TV", "price": 13299.0, "tag": "家電"},
    {"sku": "157137", "name": "Honeywell 吸塵器", "price": 6999.0, "tag": "家電"},
]


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


# ----------------------- JSON persistence SSOT -----------------------
def test_load_missing_artifact_returns_empty(tmp_path):
    assert history.load_observations(str(tmp_path / "nope.json")) == []


def test_dump_is_deterministic_roundtrip(tmp_path):
    art = str(tmp_path / "h.json")
    c = history.connect(":memory:")
    history.seed_from_snapshot(ITEMS, conn=c)
    n = history.export_observations(c, art)
    assert n == 5 * 14
    back = history.load_observations(art)
    assert len(back) == n
    assert history.load_observations(art) == back        # stable bytes
    c.close()


def test_replay_rebuilds_series_from_json(tmp_path):
    art = str(tmp_path / "h.json")
    c = history.connect(":memory:")
    history.seed_from_snapshot(ITEMS, conn=c)
    history.export_observations(c, art)
    c.close()
    # a brand-new connection rebuilds the whole series from the JSON artifact
    g = history.connect(":memory:")
    obs = history.load_observations(art)
    history.replay(conn=g, observations=obs)
    assert len(history.series("3062725", g)) == 14
    g.close()


def test_append_real_grows_the_json_artifact(tmp_path):
    """The scheduled job grows history_data.json: backfill + one real day."""
    art = str(tmp_path / "h.json")
    c = history.connect(":memory:")
    history.seed_from_snapshot(ITEMS, conn=c)
    history.export_observations(c, art)
    c.close()
    added = history.append_real(ITEMS, today="2026-11-02", persist_path=art)
    assert added == 5                                   # 5 skus, one real point
    g = history.connect(":memory:")
    history.replay(conn=g, observations=history.load_observations(art))
    assert len(history.series("139339", g)) == 15       # 14 backfill + 1 real
    g.close()


def test_append_real_idempotent_same_day(tmp_path):
    """A same-day re-run is a no-op; a new day extends the series."""
    art = str(tmp_path / "h.json")
    history.dump_observations([], art)                  # start from nothing
    assert history.append_real(ITEMS, today="2026-11-02", persist_path=art) == 5
    assert history.append_real(ITEMS, today="2026-11-02", persist_path=art) == 0  # dedup
    assert history.append_real(ITEMS, today="2026-11-03", persist_path=art) == 5   # new day
    assert history.append_real(ITEMS, today="2026-11-03", persist_path=art) == 0


def test_append_real_skips_unpriced_items(tmp_path):
    art = str(tmp_path / "h.json")
    history.dump_observations([], art)
    items = [
        {"sku": "a", "name": "Free", "price": None},
        {"sku": "b", "name": "Zero", "price": 0},
        {"sku": "c", "name": "OK", "price": 42.0},
    ]
    assert history.append_real(items, today="2026-11-02", persist_path=art) == 1
    obs = history.load_observations(art)
    assert [o["sku"] for o in obs] == ["c"]


def test_current_prefers_real_over_later_backfill():
    """A real obs (dated earlier on the day) must outrank a later-timestamped
    deterministic backfill point for 'current' — the headline is a real scrape,
    not the synthetic shape, whenever any real point exists."""
    c = history.connect(":memory:")
    history.record([{"sku": "q", "name": "Widget", "price": 900.0, "tag": "3C"}],
                   ts="2026-01-11T16:00:00", source="backfill", synthetic=True, conn=c)
    history.record([{"sku": "q", "name": "Widget", "price": 825.0, "tag": "3C"}],
                   ts="2026-01-11T00:00:00",            # real, earlier in the day
                   conn=c)
    m = history.metrics("q", c)
    assert m["current"] == 825.0            # not the 16:00 backfill
    assert m["current_is_real"] is True
    assert m["real_points"] == 1
    assert m["last_seen"] == "2026-01-11T00:00:00"
    c.close()


def test_current_falls_back_to_backfill_when_no_real():
    c = history.connect(":memory:")
    history.record([{"sku": "p", "name": "X", "price": 100.0, "tag": "3C"}],
                   ts="2026-01-10T00:00:00", source="backfill", synthetic=True, conn=c)
    m = history.metrics("p", c)
    assert m["current"] == 100.0
    assert m["current_is_real"] is False
    assert m["real_points"] == 0
    c.close()
