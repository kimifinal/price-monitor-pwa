"""Reproducible generator for the frontend's baked-in offline snapshots (issue #6).

Issue #6 makes the PWA fully offline: the service worker (frontend/src/sw.js)
serves /api/costco/history and /api/crypto from the response cache, then falls
back to a COMMITTED snapshot so the 歷史價格比價 cards render with no network.
This script regenerates those two committed JSON files from the live backend
API — the git-diffable SSOT the offline fallback renders from.

It is NOT wired into CI (the snapshot only needs refreshing when the backend's
history changes); run it locally after a data refresh:

    cd backend && python ../scripts/render_history_snapshot.py

Costco items carry per-sku series so the offline sparkline can be drawn; crypto
items already arrive with their series.
"""
import json
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "snapshot"))

sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient  # noqa: E402
import main as backend_main  # noqa: E402  (avoid clobbering the module with the render() fn)


def enrich_costco_series(client: TestClient, payload: dict) -> dict:
    """/api/costco/history items have metrics+verdict but no per-point series;
    fetch each sku's series so the offline snapshot can draw a sparkline."""
    for item in payload.get("items", []):
        sku = item.get("sku")
        if not sku:
            continue
        resp = client.get(f"/api/costco/history/{sku}")
        if resp.status_code == 200:
            item["series"] = resp.json().get("series", [])
    return payload


def main() -> None:
    client = TestClient(backend_main.app)
    costco = client.get("/api/costco/history").json()
    enrich_costco_series(client, costco)
    crypto = client.get("/api/crypto").json()

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "costco-history.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "snapshot_for": "/api/costco/history",
                "generated_by": "scripts/render_history_snapshot.py",
                "count": costco.get("count", 0),
                "items": costco.get("items", []),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(os.path.join(OUT_DIR, "crypto.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "snapshot_for": "/api/crypto",
                "generated_by": "scripts/render_history_snapshot.py",
                "count": crypto.get("count", 0),
                "items": crypto.get("items", []),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"wrote {OUT_DIR}/costco-history.json "
        f"({len(costco.get('items', []))} items, "
        f"{sum(1 for i in costco.get('items', []) if i.get('series'))} with series)"
    )
    print(
        f"wrote {OUT_DIR}/crypto.json "
        f"({len(crypto.get('items', []))} items, "
        f"{sum(1 for i in crypto.get('items', []) if i.get('series'))} with series)"
    )


if __name__ == "__main__":
    main()
