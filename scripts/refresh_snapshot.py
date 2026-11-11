#!/usr/bin/env python3
"""Refresh the offline Costco snapshot (DEMO_BASKET) and push it when it changes.

Why this exists ("接 4"): the live BFS crawl costs ~18-30s. That cost must NOT
sit on the request path. A scheduled job (local cron / GitHub Actions) runs THIS
periodically to keep `backend/costco_data.py` fresh; the FastAPI endpoint always
serves the pre-snapshotted basket, so user-facing latency stays ~0ms.

Idempotent + scheduler-safe:
  - only commits + pushes when the snapshot actually changed;
  - a day where nothing moved leaves the tree clean and exits 0;
  - a failed crawl never corrupts the existing snapshot (it is left untouched).

Usage:
  python3 scripts/refresh_snapshot.py            # crawl + regenerate + push if changed
  python3 scripts/refresh_snapshot.py --dry-run  # crawl + regenerate, show diff, no push
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SNAPSHOT = "backend/costco_data.py"


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

    # 3. Commit + push only if the snapshot file actually changed.
    st = run("git", "status", "--porcelain", "--", SNAPSHOT)
    if not st.stdout.strip():
        print("no change — snapshot already up to date (no-op)")
        return 0

    if dry_run:
        diff = run("git", "diff", "--stat", "--", SNAPSHOT)
        print(f"[dry-run] would refresh {SNAPSHOT}:")
        print(diff.stdout.strip())
        print("[dry-run] not committing/pushing")
        run("git", "checkout", "--", SNAPSHOT)  # keep tree clean
        return 0

    run("git", "add", SNAPSHOT)
    msg = f"chore(snapshot): refresh Costco basket ({len(items)} items {by_tag})"
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
