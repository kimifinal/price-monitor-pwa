"""Issue #10 — IDEMPOTENCE GUARD on the frontend offline snapshot.

Proves the offline snapshot rendered by `scripts/render_history_snapshot.py` is
BYTE-DETERMINISTIC from the SSOT (history_data.json + DEMO_BASKET): rendering
twice from the same inputs yields identical bytes, and a re-render matches the
committed `frontend/public/snapshot/costco-history.json` exactly.

This is the "history_data.json 重跑 byte 一致" AC from the issue's roadmap —
the rendered artifact must be reproducible (no wall-clock / dict-order drift) so
the CI step that re-renders and runs `git diff --exit-code` can stay green, and
a stale/rotted committed snapshot fails the build (issue #3b).

Note: retention-window byte-identity is already pinned in test_retention.py; this
guards the RENDERED snapshot specifically — different artifact, different path.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RENDER_PY = ROOT / "scripts" / "render_history_snapshot.py"
COMMITTED = ROOT / "frontend" / "public" / "snapshot" / "costco-history.json"


def _load_render():
    spec = importlib.util.spec_from_file_location(
        "render_history_snapshot", str(RENDER_PY)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_snapshot_is_byte_deterministic(tmp_path):
    """Rendering the same SSOT twice produces identical bytes (and identical
    on-disk files) — byte-deterministic, no churn."""
    m = _load_render()
    a = m.render_snapshot(out_dir=str(tmp_path / "a"),
                         backend_dir=str(ROOT / "backend"))
    b = m.render_snapshot(out_dir=str(tmp_path / "b"),
                         backend_dir=str(ROOT / "backend"))
    assert a == b                                   # returned text identical
    fa = (tmp_path / "a" / "costco-history.json").read_bytes()
    fb = (tmp_path / "b" / "costco-history.json").read_bytes()
    assert fa == fb                                 # on-disk bytes identical
    assert fa, "rendered snapshot must not be empty"


def test_render_snapshot_matches_committed(tmp_path):
    """A freshly rendered snapshot equals the COMMITTED one — i.e. the repo's
    snapshot is up to date. This is the local face of CI's `git diff
    --exit-code` (a stale committed snapshot makes this fail, then CI too)."""
    m = _load_render()
    rendered = m.render_snapshot(out_dir=str(tmp_path / "c"),
                                backend_dir=str(ROOT / "backend"))
    committed = COMMITTED.read_text(encoding="utf-8")
    assert rendered == committed


def test_render_snapshot_does_not_open_a_db(tmp_path, monkeypatch, capsys):
    """The render path is JSON-only: it must not create/open an on-disk price db."""
    backend_dir = ROOT / "backend"
    # A stray db, if created, would land here via the module's DEFAULT_DB.
    stray = backend_dir / "price_history.db"
    if stray.exists():
        stray.unlink()
    m = _load_render()
    try:
        m.render_snapshot(out_dir=str(tmp_path / "d"), backend_dir=str(backend_dir))
    finally:
        pass
    assert not stray.exists(), "a .db must not be touched by the render path"
