"""Reproducible generator for the frontend's baked-in offline snapshot (issue #6).

Issue #6 makes the PWA fully offline: the service worker (frontend/src/sw.js)
serves /api/costco/history from the response cache, then falls back to a COMMITTED
snapshot so the 歷史價格比價 cards render with no network. This script regenerates
that committed JSON file from the live backend API — the git-diffable SSOT the
offline fallback renders from.

It is NOT wired into CI (the snapshot only needs refreshing when the backend's
history changes); run it locally after a data refresh:

    cd backend && python ../scripts/render_history_snapshot.py

Costco items carry per-sku series so the offline sparkline can be drawn.
"""
import json
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "snapshot"))

# NOTE: BACKEND_DIR is placed on `sys.path` and `os.chdir` is performed LAZILY,
# inside render_snapshot(), not at import time — so merely importing this module
# (e.g. from the idempotence pytest) has NO side effects that could disturb a
# shared test session (no import-time chdir). The renderer rebuilds the snapshot
# from the JSON SSOT only (history_data.json + DEMO_BASKET), never a .db.


def enrich_costco_series(client, payload: dict) -> dict:
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


def render_snapshot(out_dir=OUT_DIR, backend_dir=BACKEND_DIR) -> str:
    """Render the offline snapshot JSON for /api/costco/history to
    `out_dir/costco-history.json` and return the exact bytes-as-text written.

    Byte-deterministic for a given SSOT: the same inputs produce identical
    bytes (the idempotence invariant — issue #10 "history_data.json 重跑 byte
    一致"). The JSON is dumped with a fixed `indent` + `ensure_ascii=False` and
    per-sku series in the same stable order the backend returns, so two renders
    are byte-identical.

    Side effects are local: it puts `backend_dir` on `sys.path`, `chdir`s to it
    so `import main` resolves the data paths the way the script does, then
    restores the original cwd. Rendering builds the in-memory store purely from
    JSON (see history.ensure_history), so it never opens a .db.
    """
    backend_dir = os.path.abspath(str(backend_dir))
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    os.makedirs(out_dir, exist_ok=True)
    prev_cwd = os.getcwd()
    os.chdir(backend_dir)
    try:
        from fastapi.testclient import TestClient
        import main as backend_main
        client = TestClient(backend_main.app)
        costco = client.get("/api/costco/history").json()
        enrich_costco_series(client, costco)
        payload = {
            "snapshot_for": "/api/costco/history",
            "generated_by": "scripts/render_history_snapshot.py",
            "count": costco.get("count", 0),
            "items": costco.get("items", []),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    finally:
        os.chdir(prev_cwd)
    out_path = os.path.join(os.path.abspath(str(out_dir)), "costco-history.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main() -> None:
    out_dir = OUT_DIR
    text = render_snapshot(out_dir=out_dir)
    payload = json.loads(text)
    print(
        f"wrote {out_dir}/costco-history.json "
        f"({len(payload.get('items', []))} items, "
        f"{sum(1 for i in payload.get('items', []) if i.get('series'))} with series)"
    )


if __name__ == "__main__":
    main()
