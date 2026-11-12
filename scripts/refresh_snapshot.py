#!/usr/bin/env python3
"""Refresh the offline Costco snapshot AND the history time series, then push.

Two artifacts keep the app fast *and* stateful:
  - backend/costco_data.py     : the current-price snapshot (DEMO_BASKET). The API
                                 serves this, so user latency stays ~0ms.
  - backend/history_data.json  : the persisted price time series (SSOT). A new
                                 real point is appended per day; the 14-day
                                 backfill seed gives the UI/tests a shape before
                                 a single real day has elapsed.

Why this exists ("接 4" + "把持久化接上"): the live BFS crawl costs ~18-30s and a
real price series only grows with elapsed days. Both are scheduled, not ad-hoc,
so they must NOT sit on the request path.

Scheduler-safe: a day where nothing moved leaves the tree clean and exits 0; a
failed crawl never corrupts the existing artifacts. history_data.json is the JSON
SSOT, so it survives ephemeral CI runners (a binary .db would not).

Usage:
  python3 scripts/refresh_snapshot.py            # crawl + regenerate + push
  python3 scripts/refresh_snapshot.py --dry-run  # crawl + regenerate, show diff, no push
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SNAPSHOT = "backend/costco_data.py"
HISTORY = "backend/history_data.json"
# The discontinued-skus sidecar (issue #5 AC3): a decoupled, git-diffable record of
# skus the rolling window evicted, so alerts/watchlist still reference them.
DISCONTINUED = "backend/history_data.discontinued.json"
# The frontend's baked-in offline snapshot (issue #6/#10): rendered from the SAME
# SSOT as `render_history_snapshot.py`. It MUST be re-rendered from the just-
# updated history_data.json and committed alongside it — otherwise the scheduled
# append+prune leaves the committed copy stale and issue #10's idempotence guard
# (CI `git diff --exit-code` on a fresh re-render, + the backend
# test_snapshot_idempotent test) starts failing. This is the #9 CI blocker.
FRONTEND_SNAPSHOT = "frontend/public/snapshot/costco-history.json"
RENDER = "scripts/render_history_snapshot.py"


def run(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, **kw)


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    # 1. Full-coverage live crawl. A refresh job is scheduled, not ad-hoc, so a
    #    slow-but-complete crawl (cap=15) is the right trade here.
    sys.path.insert(0, str(BACKEND))
    try:
        from costco import basket
        items: list[dict] = basket(
            live=True, delay=0.1, workers=8, timeout=5, per_tag_cap=15
        )
    except Exception as e:  # noqa: BLE001 — a scheduler must never crash on us
        print(f"! live crawl failed ({e!r}) — existing snapshot left unchanged")
        return 0

    by_tag: dict[str, int] = {}
    for p in items:
        tag = p.get("tag", "?")
        by_tag[tag] = by_tag.get(tag, 0) + 1
    print(f"crawled {len(items)} items {by_tag}")

    if not items:
        print("! empty crawl — refusing to wipe the snapshot, leaving it intact")
        return 0

    # 2. Regenerate costco_data.py from the freshly crawled basket.
    dump = Path(tempfile.gettempdir()) / "snapshot_dump.json"
    dump.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    r = run("python3", "backend/gen_costco_data.py", str(dump))
    if r.returncode != 0:
        print("gen_costco_data.py failed:\n", r.stderr)
        return 1
    # Sanity: the regenerated snapshot MUST import and expose a non-empty basket.
    chk = subprocess.run(
        ["python3", "-c",
         "from costco_data import DEMO_BASKET as B; import sys;"
         " sys.exit(0 if any('name' in p and 'price' in p for p in B) else 1)"],
        cwd=str(BACKEND), text=True, capture_output=True,
    )
    if chk.returncode != 0:
        print("! regenerated snapshot failed import/shape check — reverting")
        run("git", "checkout", "--", SNAPSHOT)
        return 1

    # 3. Grow the persisted time series with today's real observation. This is the
    #    step that turns the JSON backfill into a *growing* real series: one new
    #    point per sku dated today. Re-running the same day is a no-op.
    from history import append_real
    added = append_real(items, persist_path=str(BACKEND / "history_data.json"))
    print(f"history_data.json: +{added} new obs ({added}/{len(items)} skus moved)")

    # 3b. Rolling-window retention (#5 — 保留策略 / drift 衛生). The append-only
    #     history_data.json would otherwise grow without bound; a window keeps only
    #     the most recent N days (HISTORY_WINDOW_DAYS, default 90). The window is
    #     anchored at the NEWEST observation so a re-run on the already-pruned file
    #     is byte-identical (idempotent diff). Discontinued skus land in a separate
    #     decoupled sidecar (never a dangling row); a discontinued sku that is also
    #     watched is merely FLAGGED — watchlist.json is NOT deleted from #4's
    #     decoupling, so retention never churns the personalization gate.
    from history import prune_to_window
    from watchlist import load as wl_load
    disc_path = str(BACKEND / "history_data.discontinued.json")
    _wal = wl_load()
    try:
        stats = prune_to_window(
            persist_path=str(BACKEND / "history_data.json"),
            discontinued_path=disc_path,
            watchlist=_wal,
        )
    except Exception as e:  # noqa: BLE001 — a scheduler must never crash on us
        print(f"! retention failed ({e!r}) — leaving artifacts as-is")
        return 1
    print(f"retention(window={stats['window_days']}d): {stats['before']} -> "
          f"{stats['after']} obs, -{stats['dropped']} evicted, "
          f"{len(stats['discontinued'])} discontinued -> sidecar")
    for _f in stats["watchlist_flags"]:
        print(f"[retention:flag] watchlist sku {_f['sku']} is discontinued — "
              f"kept in watchlist.json (flagged, not deleted)")

    # 3c. Re-render the frontend offline snapshot from the JUST-updated SSOT (step
    #     1+3+3b above) so it is committed in lock-step with history_data.json.
    #     This is the fix that keeps issue #10's idempotence guard green after
    #     every scheduled refresh: without it the append+prune grows the series
    #     (30 -> N skus) but the committed frontend snapshot stays frozen, so the
    #     CI `git diff --exit-code` on a fresh re-render -- and the backend
    #     test_snapshot_idempotent -- diverge. render_history_snapshot.render is
    #     pure-Python / JSON-only / byte-deterministic (no network, no .db), and
    #     its side effects are LOCAL + lazy, so importing it here is safe.
    _render_spec = importlib.util.spec_from_file_location(
        "render_history_snapshot", str(ROOT / RENDER)
    )
    _render_mod = None
    if _render_spec is not None and _render_spec.loader is not None:
        _render_mod = importlib.util.module_from_spec(_render_spec)
        _render_spec.loader.exec_module(_render_mod)
    try:
        assert _render_mod is not None, f"could not load {RENDER}"
        _render_mod.render_snapshot()
    except Exception as e:  # noqa: BLE001 — surface the failure, never leave a
        # half-rendered / truncated snapshot on disk that would fool CI.
        print(f"! frontend snapshot re-render failed ({e!r}) — aborting, tree left untouched")
        run("git", "checkout", "--", FRONTEND_SNAPSHOT)
        return 1
    print(f"re-rendered {FRONTEND_SNAPSHOT} from updated history_data.json "
          f"(offline, byte-deterministic)")

    # 4. Commit + push only when an artifact actually changed.
    st = run("git", "status", "--porcelain", "--",
             SNAPSHOT, HISTORY, DISCONTINUED, FRONTEND_SNAPSHOT)
    if not st.stdout.strip():
        print("no change — artifacts already up to date (no-op)")
        return 0

    if dry_run:
        diff = run("git", "diff", "--stat", "--",
                   SNAPSHOT, HISTORY, DISCONTINUED, FRONTEND_SNAPSHOT)
        print(f"[dry-run] would refresh {SNAPSHOT} + {HISTORY} + {DISCONTINUED} "
              f"+ {FRONTEND_SNAPSHOT}:")
        print(diff.stdout.strip())
        print("[dry-run] not committing/pushing")
        # Keep the tree clean. A first-ever sidecar is untracked (git checkout of it
        # errors), so if the checkout reports that, drop the freshly-written copy.
        rc = run("git", "checkout", "--", SNAPSHOT, HISTORY, DISCONTINUED, FRONTEND_SNAPSHOT)
        if rc.returncode != 0 and os.path.exists(disc_path):
            os.remove(disc_path)
            run("git", "checkout", "--", SNAPSHOT, HISTORY, FRONTEND_SNAPSHOT)
        return 0

    run("git", "add", SNAPSHOT, HISTORY, DISCONTINUED, FRONTEND_SNAPSHOT)
    msg = (f"chore(data): refresh snapshot + history (+ frontend offline snapshot) — "
           f"{len(items)} items {by_tag}, +{added} costco obs, "
           f"retention -{stats['dropped']} ({stats['window_days']}d window)")
    c = run("git", "commit", "-m", msg)
    if c.returncode != 0:
        print("commit failed:\n", c.stderr)
        return 1
    p = run("git", "push")
    if p.returncode != 0:
        print("push failed:\n", p.stderr)
        return 1
    print(f"pushed refresh ({len(items)} items {by_tag}) -> {run('git', 'rev-parse', '--short', 'HEAD').stdout.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
