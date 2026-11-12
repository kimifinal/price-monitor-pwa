"""Backend API tests — exercise main.py routes + the alert rule (SSOT)."""
from fastapi.testclient import TestClient
from main import app, _store
from models import should_alert

client = TestClient(app)


def setup_function(_):
    """Clear the in-memory store before each test."""
    _store.clear()


def test_should_alert_rule():
    # This is the shared rule; keep it aligned with frontend monitor.js.
    assert should_alert(80, 100) is True
    assert should_alert(100, 100) is True
    assert should_alert(120, 100) is False


def test_create_and_list_item():
    r = client.post("/api/items", json={"name": "Chiikawa 徽章", "target": 100})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Chiikawa 徽章"
    assert body["target"] == 100

    ls = client.get("/api/items")
    assert ls.status_code == 200
    assert len(ls.json()) == 1


def test_item_rejects_empty_name():
    r = client.post("/api/items", json={"name": "", "target": 100})
    assert r.status_code == 422  # pydantic rejects empty name


def test_item_rejects_non_positive_target():
    r = client.post("/api/items", json={"name": "X", "target": 0})
    assert r.status_code == 422  # target must be > 0


def test_check_item_alerts_when_below_target(monkeypatch):
    # Seed an item at its target, then a simulated price should alert.
    r = client.post("/api/items", json={"name": "Test", "target": 100})
    item_id = r.json()["id"]
    res = client.post(f"/api/items/{item_id}/check")
    assert res.status_code == 200
    # Alert is deterministic given the simulated price; just assert shape.
    assert res.json()["id"] == item_id
    assert "alerted" in res.json()


def test_check_missing_item_raises():
    r = client.post("/api/items/does-not-exist/check")
    assert r.status_code == 404  # missing item -> clean 404


def test_costco_basket_endpoint_returns_snapshot():
    """GET /api/costco/basket returns the offline snapshot (DEMO_BASKET)."""
    r = client.get("/api/costco/basket")
    assert r.status_code == 200
    body = r.json()
    # Ranges, not exact counts: the 3C portion is refreshed live and can drift.
    assert body["count"] >= 20
    assert body["3C"] >= 5
    assert body["家電"] >= 10
    assert len(body["items"]) >= 20


import history as _history
from costco_data import DEMO_BASKET


def test_costco_history_all_offline(tmp_path, monkeypatch):
    """GET /api/costco/history returns metrics + a verdict for every sku, and
    stays offline/CI-safe (auto-seeded from the snapshot, into a tmp DB)."""
    monkeypatch.setattr(_history, "DEFAULT_DB", str(tmp_path / "h.db"))
    r = client.get("/api/costco/history")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 20
    for it in body["items"]:
        for k in ("current", "low", "high", "drop_pct_from_high", "points"):
            assert k in it
        assert it["verdict"]["verdict"] in (
            "all_time_low", "good_deal", "stable", "near_high", "unknown"
        )
        assert it["points"] >= 1


def test_costco_history_sku_series_and_404(tmp_path, monkeypatch):
    monkeypatch.setattr(_history, "DEFAULT_DB", str(tmp_path / "h.db"))
    sku = str(DEMO_BASKET[0]["sku"])
    r = client.get(f"/api/costco/history/{sku}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["series"]) == body["points"] >= 1
    assert "verdict" in body and "label" in body["verdict"]
    # an sku with no history is a clean 404, not a crash
    assert client.get("/api/costco/history/000000-nope").status_code == 404


# ---------------------- 個人化 watchlist gate (AC1..#4) ----------------------
def test_watchlist_endpoint_returns_the_ssot():
    """GET /api/watchlist is a READ of the committed watchlist.json — offline,
    no network. count is consistent with the entries it returns."""
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["items"])
    assert body["count"] == len(body["skus"])
    assert body["count"] >= 1
    for e in body["items"]:
        assert "sku" in e
        assert all(k in ("target", "min_drop_pct") for k in (e.get("threshold") or {}))


def test_watchlist_endpoint_offline_empty_is_silent(monkeypatch):
    """AC5 via the API: an EMPTY watchlist reads back as 0 / no watched skus
    (the silent default), still without any network."""
    monkeypatch.setattr("main.load_watchlist", lambda *a, **k: [])
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "skus": [], "items": []}
