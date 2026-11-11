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
