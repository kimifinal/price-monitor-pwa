"""Issue #10 — NO .DB-LEAK GUARD.

Two guarantees for the API's read-model (`/api/costco/history` ->
`history.ensure_history`):

 (a) FRESH env (no price_history.db on disk): the endpoint returns EXACTLY the
     rows derived from `backend/history_data.json`, and NO .db file is ever
     opened — the API rebuilds an in-memory store from JSON only.

 (b) STALE .db: drop an on-disk `price_history.db` seeded with EXTRA / OLD rows
     that are NOT in history_data.json, point `DEFAULT_DB` at it, and prove the
     API STILL returns only the JSON-sourced data — the stale-only skus must not
     appear. This is a regression lock: if anyone reverts `ensure_history` to read
     the on-disk store, this test fails.

The lock is enforced by patching `history.connect` to REFUSE any on-disk path
(only `:memory:` is allowed), so the proof is "the API never even asks for a
disk store", and we additionally assert the on-disk file never materialises.
"""
import os

import pytest
from fastapi.testclient import TestClient

import history
import main
from models import price_verdict


# --------------------------------------------------------------------------
# the "no on-disk store is ever opened" sentinel
# --------------------------------------------------------------------------
@pytest.fixture()
def no_disk_conn(monkeypatch, tmp_path):
    """Refuse any on-disk sqlite open; only `:memory:` may be requested.

    A regression (re-reading the on-disk store) raises AssertionError the instant
    the API asks connect() for a real path — turning the guard red.
    """
    opens = []
    real_connect = history.connect

    def guarded_connect(path=None, *args, **kwargs):
        if path is not None and path != ":memory:":
            raise AssertionError(
                f"no-.db-leak VIOLATION: history.connect opened an on-disk store "
                f"{path!r} — the API must rebuild from JSON only"
            )
        opens.append(path)
        return real_connect(path, *args, **kwargs)

    # A non-existent on-disk target: if the code ever fell back to DEFAULT_DB it
    # would materialise this file, which we explicitly assert stays absent.
    monkeypatch.setattr(history, "DEFAULT_DB", str(tmp_path / "nope.db"))
    monkeypatch.setattr(history, "connect", guarded_connect)
    return tmp_path, opens


def _golden_from_json() -> dict:
    """The per-sku metrics+verdict that history_data.json IMPLIES, built in an
    independent fresh in-memory store (so it cannot be contaminated by the API's
    own store). This is the JSON-sourced ground truth the API must equal."""
    obs = history.load_observations()
    conn = history.connect(":memory:")
    history.replay(conn, obs)
    out = {}
    for sku in history.all_sellers(conn):
        m = dict(history.metrics(sku, conn=conn))
        m["verdict"] = price_verdict(m)
        out[str(sku)] = m
    conn.close()
    return out


def _api_items(client: TestClient) -> dict:
    body = client.get("/api/costco/history").json()
    assert body["count"] == len(body["items"])
    return {it["sku"]: it for it in body["items"]}


# --------------------------------------------------------------------------
# (a) fresh env — API == JSON, and no .db is opened or created
# --------------------------------------------------------------------------
def test_fresh_env_api_equals_json_and_no_db_opened(no_disk_conn):
    tmp_path, opens = no_disk_conn
    # nothing on disk yet
    assert not os.path.exists(tmp_path / "nope.db")

    client = TestClient(main.app)
    got = _api_items(client)
    golden = _golden_from_json()

    # the sku SET is exactly the JSON's — no extra (leaked) skus at all
    assert got and set(got) == set(golden)

    # per-sku current + verdict match the JSON-derived ground truth
    for sku, gm in golden.items():
        ag = got[sku]
        assert ag["current"] == gm["current"]
        assert ag["low"] == gm["low"]
        assert ag["high"] == gm["high"]
        assert ag["drop_pct_from_high"] == gm["drop_pct_from_high"]
        assert ag["at_all_time_low"] == gm["at_all_time_low"]
        assert ag["points"] == gm["points"]
        assert ag["verdict"] == gm["verdict"]

    # every store the API touched was in-memory; on-disk file never materialised
    assert all(p is None or p == ":memory:" for p in opens)
    assert not os.path.exists(tmp_path / "nope.db")


# --------------------------------------------------------------------------
# (b) stale .db with rows NOT in the JSON must still not leak
# --------------------------------------------------------------------------
def test_stale_on_disk_db_does_not_leak_into_api(no_disk_conn, monkeypatch):
    import sqlite3

    tmp_path, _opens = no_disk_conn

    # A stale on-disk store seeded with (1) a brand-new sku absent from the JSON
    # and (2) an OLD, wrong "current" for a sku that IS in the JSON.
    stale = tmp_path / "stale_price_history.db"
    conn = sqlite3.connect(stale)
    conn.row_factory = sqlite3.Row
    history.init_db(conn)
    history.record(
        [{"sku": "999999", "name": "Leak Probe SKU", "price": 1.0, "tag": "3C"}],
        ts="2020-01-01T00:00:00", source="costco", conn=conn,
    )
    history.record(
        [{"sku": "139339", "name": "PQI", "price": 5.0, "tag": "3C"}],
        ts="2020-01-01T00:00:00", source="costco", conn=conn,
    )
    conn.commit()
    conn.close()

    # Point the code's on-disk store at the stale file. With the guard active the
    # API must still ignore it entirely.
    monkeypatch.setattr(history, "DEFAULT_DB", str(stale))
    assert stale.exists()

    client = TestClient(main.app)
    got = _api_items(client)
    golden = _golden_from_json()

    # the leaked-only sku never appears, and the sku set is still exactly JSON's
    assert "999999" not in got
    assert set(got) == set(golden)

    # 139339's "current" must be the JSON value, NOT the stale 5.0
    if "139339" in golden:
        assert got["139339"]["current"] == golden["139339"]["current"]
        assert got["139339"]["current"] != 5.0
        assert got["139339"]["verdict"] == golden["139339"]["verdict"]


# --------------------------------------------------------------------------
# direct contract on the read-model path itself (belt-and-suspenders)
# --------------------------------------------------------------------------
def test_ensure_history_rebuilds_from_json_ignoring_on_disk(monkeypatch, tmp_path):
    """The underlying entry (bypassing the HTTP layer) rebuilds from JSON even
    when a stale on-disk DEFAULT_DB exists."""
    import sqlite3

    stale = tmp_path / "stale.db"
    c = sqlite3.connect(str(stale))
    c.row_factory = sqlite3.Row
    history.init_db(c)
    history.record(
        [{"sku": "888888", "name": "Stale-only", "price": 9.0, "tag": "3C"}],
        ts="2019-01-01T00:00:00", source="costco", conn=c,
    )
    c.commit()
    c.close()

    monkeypatch.setattr(history, "DEFAULT_DB", str(stale))
    conn = history.ensure_history(persist_path=history.PERSIST_PATH)
    try:
        skus = {str(r["sku"]) for r in conn.execute(
            "SELECT sku FROM observations").fetchall()}
    finally:
        conn.close()
    # the stale-only sku never got in; the store is exactly the JSON's skus
    assert "888888" not in skus
    golden = _golden_from_json()
    assert skus == set(golden)
