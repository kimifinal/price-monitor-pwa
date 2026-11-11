#!/usr/bin/env python3
"""Refresh the offline Costco snapshot AND the history time series, then push.

Two artifacts keep the app fast *and* stateful:
  - backend/costco_data.py     : the current-price snapshot (DEMO_BASKET). The API
                                 serves this, so user latency stays ~0ms.
  - backend/history_data.json  : the persisted price time series (SSOT). A new
                                 real point is appended per day; the 14-day
                                 backfill seed gives the UI/tests a shape before
                                 a single real day has elapsed.
  - backend/crypto.py          : the coingecko refresh (source='coingecko'), which
                                 appends into the SAME history_data.json — the
                                 multi-source 時序 layer #3 asks for.

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

    # 3b. Grow the CRYPTO series in the SAME history_data.json (source='coingecko').
    # CoinGecko is just another source in the multi-source 時序 layer (#3) — coexisting
    # with Costco in one file. Offline-safe by construction: a failed live fetch yields
    # per-coin *synthetic* points that never crash the job, and their synthetic flag
    # keeps the real-only alert scanner from firing on a fallback price.
    from crypto import ensure_crypto_series, append_crypto, fetch_crypto_items
    ensure_crypto_series(persist_path=str(BACKEND / "history_data.json"))  # bootstrap a fresh checkout
    citems = fetch_crypto_items(live=True)
    crypto_added = append_crypto(items=citems, persist_path=str(BACKEND / "history_data.json"))
    print(f"coingecko: +{crypto_added} new obs / {len(citems)} coins")

    # 4. Commit + push only when an artifact actually changed.
    st = run("git", "status", "--porcelain", "--", SNAPSHOT, HISTORY)
    if not st.stdout.strip():
        print("no change — artifacts already up to date (no-op)")
        return 0

    if dry_run:
        diff = run("git", "diff", "--stat", "--", SNAPSHOT, HISTORY)
        print(f"[dry-run] would refresh {SNAPSHOT} + {HISTORY}:")
        print(diff.stdout.strip())
        print("[dry-run] not committing/pushing")
        run("git", "checkout", "--", SNAPSHOT, HISTORY)  # keep tree clean
        return 0

    run("git", "add", SNAPSHOT, HISTORY)
    msg = (f"chore(data): refresh snapshot + history — "
           f"{len(items)} items {by_tag}, +{added} costco obs, +{crypto_added} coingecko obs")
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
