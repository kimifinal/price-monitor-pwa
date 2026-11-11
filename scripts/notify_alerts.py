#!/usr/bin/env python3
"""Fire price alerts (#2) off the request path, deduped, offline-safe.

The scan reads the persisted time series (`backend/history.py` →
`history_data.json`, the SSOT), turns each SKU into a verdict via
`models.price_verdict` (the one rule), and — for any SKU that *crosses* an alarm
verdict AND isn't already in the dedup state — emits it through a sink.

Golden rules baked in:
  * NEVER fire on synthetic/fallback data (`current_is_real == False` -> skip).
    So an offline / no-network run cannot produce a false "buy now".
  * "Notify once per event": a git-tracked `alerts_state.json` is the dedup SSOT,
    so the same verdict on the same day is not re-sent even across ephemeral CI
    runners.
  * Delivery goes through a pluggable sink: `log` (default, always CI-green),
    `telegram` (needs TELEGRAM_BOT_TOKEN+CHAT_ID, no-ops otherwise), or `github`
    (append a digest comment to one 🚨 issue; needs only the Actions GITHUB_TOKEN).

Usage:
  python3 scripts/notify_alerts.py                 # scan + log, no push
  python3 scripts/notify_alerts.py --sink telegram # send when creds present
  python3 scripts/notify_alerts.py --sink github   # append a digest comment
  python3 scripts/notify_alerts.py --dry-run       # scan + show, no commit/push
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
STATE = "backend/alerts_state.json"
os.environ.setdefault("PYTHONPATH", str(BACKEND))
sys.path.insert(0, str(BACKEND))


def run(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), cwd=str(ROOT), text=True, capture_output=True, **kw)


def _limit() -> int:
    """Deliver up to N alert(s), biggest % drop first. 0 / absent = no limit.

    The dedup state is still advanced on the *full* fresh set, so a capped-out
    item is not silently re-fired on the next run.
    """
    argv = sys.argv
    if "--limit" in argv:
        try:
            return int(argv[argv.index("--limit") + 1])
        except (ValueError, IndexError):
            return 0
    return 0


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    sink = "log"
    if "--sink" in sys.argv:
        sink = sys.argv[sys.argv.index("--sink") + 1]
    limit = _limit()

    import history          # noqa: E402
    from alerts import scan, load_state, save_state, emit  # noqa: E402

    # 1. Load the persisted time series (falls back to the committed snapshot).
    conn = history.ensure_history()
    metrics_list = [history.metrics(s, conn) for s in history.all_sellers(conn)]

    # 2. Deduped scan against the durable state.
    state = load_state(str(BACKEND / "alerts_state.json"))
    fresh, new_state = scan(metrics_list, state=state)
    print(f"scan: {len(metrics_list)} skus, {len(fresh)} new alert(s), sink={sink}")

    # 3. Persist the dedup state (git SSOT) on the FULL fresh set.
    save_state(new_state, str(BACKEND / "alerts_state.json"))

    # 4. Deliver (a --limit caps what is *sent*; the dedup state already consumed
    #    all `fresh`, so capped-out items won't re-fire later).
    to_emit = fresh
    if limit:
        to_emit = sorted(fresh, key=lambda a: a["drop_pct"], reverse=True)[:limit]
    token = os.environ.get("GITHUB_TOKEN", "")
    emitted = emit(to_emit, sink=sink, token=token)
    if not fresh:
        print("no new alerts (nothing to do)")

    if dry_run:
        if new_state != state:
            run("git", "checkout", "--", STATE)
        print("[dry-run] not committing/pushing")
        return 0

    # 5. Commit + push the dedup state if it actually changed.
    st = run("git", "status", "--porcelain", "--", STATE)
    if st.stdout.strip():
        run("git", "add", STATE)
        msg = f"chore(alerts): dedup state update ({emitted} new alert(s), sink={sink})"
        c = run("git", "commit", "-m", msg)
        if c.returncode != 0:
            print("commit failed:\n", c.stderr)
            return 1
        p = run("git", "push")
        if p.returncode != 0:
            print("push failed:\n", p.stderr)
            return 1
        print(f"pushed alert state -> {run('git', 'rev-parse', '--short', 'HEAD').stdout.strip()}")
    else:
        print("dedup state unchanged — no-op")
    return 0


if __name__ == "__main__":
    sys.exit(main())
