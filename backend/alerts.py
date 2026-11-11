"""Alerts — the "last mile" of the verdict (#2).

Two alert concepts live here:

1. target-price alert (legacy) — `should_alert(price, target)` in models.py +
   `send_telegram_alert(item, price)`. Kept for backwards compatibility.

2. verdict-based alert (the #2 feature) — `scan()` decides "should I shout" by
   REUSING the single source of truth `models.price_verdict`, so the trigger rule
   can never drift between the frontend JS mirror and the backend. Delivery goes
   through a sink (log / telegram / github). A deterministic dedup state
   (`alerts_state.json`, git SSOT) makes "notify once per event" hold across runs,
   including ephemeral CI runners.

Golden rule (a hard AC of #2): **never fire on synthetic/fallback data**. An SKU
that has only a 14-day backfill (`current_is_real == False`) can never be alerted,
so an offline / fallback pipeline cannot produce false "buy now" shouts.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional

from models import price_verdict   # the SSOT — we never re-implement the rule here
from watchlist import find_entry, threshold_met   # the #4 per-item gate (its SSOT)

# --------------------------------------------------------------------------
# delivery (Telegram)
# --------------------------------------------------------------------------
BOT_API = "https://api.telegram.org/bot{token}/sendMessage"


def _telegram_send(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False                          # no creds -> not attempted
    url = BOT_API.format(token=token) + f"?chat_id={chat_id}&text=" + urllib.parse.quote(text)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="POST", data=b""),
                                    timeout=10) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def send_telegram_alert(item, price) -> bool:
    """Legacy target-price Telegram sink. Kept for backwards compatibility.

    Returns True when a real send was attempted ok, False when no creds are set
    (so the pipeline runs without them).
    """
    name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else str(item))
    target = getattr(item, "target", None) or (item.get("target") if isinstance(item, dict) else None)
    return _telegram_send(f"🔔 跌破目標價\n{name}: ${price:.2f}" + (f"（目標 ${target:.2f}）" if target else ""))


# --------------------------------------------------------------------------
# verdict-based scanner (the #2 feature, on the price_verdict SSOT)
# --------------------------------------------------------------------------
STATE_PATH = os.path.join(os.path.dirname(__file__), "alerts_state.json")
DEFAULT_POLICY = {"alarm_verdicts": ("all_time_low", "good_deal")}


def _alert_verdicts(policy: Optional[dict]) -> set:
    return set((policy or DEFAULT_POLICY).get("alarm_verdicts", DEFAULT_POLICY["alarm_verdicts"]))


def alert_for(m: dict, policy: Optional[dict] = None,
              watchlist: Optional[list] = None) -> Optional[dict]:
    """One SKU's metrics -> an alert dict when it trips an ALARM verdict, else None.

    Reuses `price_verdict` (the SSOT) so the "what counts as a good time to buy"
    rule is defined in exactly one place. Two hard guarantees:
      * returns None for an empty/sparse series, and
      * returns None for `current_is_real == False` — never fire on the synthetic
        backfill. That is what keeps an offline / fallback pipeline from shouting.

    The #4 GATE: when `watchlist` is passed, only skus that are IN the watchlist
    AND meet their OWN per-item `threshold` may fire — so an unwatched sku never
    alerts (even at an all-time low) and an empty watchlist stays silent. When
    `watchlist is None` the gate is off (legacy verdict-only behaviour, which the
    existing suite relies on). The verdict itself is still sourced from
    `price_verdict`; the watchlist + threshold only decides *which* verdicts may
    come through.
    """
    if not m or not m.get("points"):
        return None
    if not m.get("current_is_real"):                # no false alerts on fallback/demo
        return None
    # The #4 gate must run BEFORE the verdict so an unwatched all-time-low never
    # even reaches the verdict comparison — a non-watchlisted sku never alerts.
    threshold = None
    if watchlist is not None:
        entry = find_entry(m, watchlist)
        if entry is None or not threshold_met(m, entry):
            return None
        threshold = entry.get("threshold")
    v = price_verdict(m)
    if v["verdict"] not in _alert_verdicts(policy):
        return None
    as_of = (m.get("last_seen") or "")[:10]
    return {
        "sku": str(m.get("sku") or m.get("name")),
        "name": m.get("name") or str(m.get("sku")),
        "tag": m.get("tag") or "",
        "verdict": v["verdict"],
        "label": v["label"],
        "drop_pct": round(v.get("drop_pct", 0.0), 1),
        "price": m.get("current"),
        "currency": m.get("currency", "TWD"),
        "url": m.get("url"),
        "as_of": as_of,
        "threshold": threshold,
    }


def alert_signature(a: dict) -> str:
    """Dedup key: one alert per (sku, verdict, day). A new verdict or a new day
    fires again; the same verdict on the same day is a no-op."""
    return f"{a['sku']}|{a['verdict']}|{a['as_of']}"


def scan(metrics_list: list[dict], state: Optional[dict] = None,
         policy: Optional[dict] = None,
         watchlist: Optional[list] = None) -> tuple[list[dict], dict]:
    """Decide which SKUs should be alerted *now*, given a dedup `state`.

    `metrics_list` is the per-SKU metrics from `history.metrics` (already carrying
    `current_is_real`). Returns `(fresh_alerts, updated_state)`; `fresh_alerts`
    are the ones NOT already in `state`.

    The #4 GATE: when `watchlist` is passed, only skus IN the watchlist that meet
    their threshold are eligible (an unwatched sku or an unmet threshold is never
    alerted); `watchlist=[]` is the silent default (nothing fires); `None` disables
    the gate (legacy verdict-only, what the existing suite assumes).
    """
    state = dict(state or {})
    fresh: list[dict] = []
    for m in metrics_list:
        a = alert_for(m, policy, watchlist)
        if not a:
            continue
        sig = alert_signature(a)
        sigs = state.setdefault(a["sku"], [])
        if sig in sigs:
            continue
        sigs.append(sig)
        a["sig"] = sig
        fresh.append(a)
    return fresh, state


def load_state(path: str = STATE_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: str = STATE_PATH) -> int:
    """Persist the dedup state deterministically (sorted, stable) so the git diff
    is reviewable and CI dedupes across ephemeral runners."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: sorted(set(v)) for k, v in state.items()},
                  f, ensure_ascii=False, indent=1, sort_keys=True)
    return sum(len(v) for v in state.values())


# --------------------------------------------------------------------------
# sinks
# --------------------------------------------------------------------------
def emit_log(alerts: list[dict]) -> int:
    for a in alerts:
        price = f"{a['price']:,.0f}" if isinstance(a["price"], (int, float)) else "n/a"
        print(f"[alert] {a['label']}  {a['name']}  ${price}{a.get('currency','')}  "
              f"({a['drop_pct']}% 距高點 · {a['verdict']})  → {a.get('url') or ''}")
    return len(alerts)


def emit_telegram(alerts: list[dict]) -> int:
    sent = 0
    for a in alerts:
        price = f"{a['price']:,.0f}" if isinstance(a["price"], (int, float)) else "n/a"
        text = (f"🔔 {a['label']}\n{a['name']}\n${price}{a.get('currency','')}"
                f"（{a['drop_pct']}% 距高點）\n{a.get('url') or ''}")
        if _telegram_send(text):
            sent += 1
        elif not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
            print(f"[alert:telegram-未配置] {a['label']} {a['name']} ${price}")
    return sent


def emit_github(alerts: list[dict], token: str = "", issue_url: str =
                "https://github.com/kimifinal/price-monitor-pwa/issues",
                issue_number: Optional[int] = None) -> int:
    """Append a single digest comment to one '🔔 價格警報' issue (no new secrets:
    only the Actions GITHUB_TOKEN is needed). Falls back to stdout without a token."""
    if not alerts:
        return 0
    lines = [f"- **{a['label']}** `{a['sku']}` {a['name']} "
             f"→ ${a['price']:,.0f}（{a['drop_pct']}% 距高點）" for a in alerts]
    body = f"#### 🔔 價格警報（{len(alerts)} 筆）\n" + "\n".join(lines)
    if not token:
        print("[alert:github-未配置 GITHUB_TOKEN] " + "\n".join(lines))
        return len(alerts)
    api = "https://api.github.com"
    # find-or-create the alerting issue
    num = issue_number
    if not num:
        try:
            req = urllib.request.Request(
                api + f"/repos/kimifinal/price-monitor-pwa/issues?state=open&per_page=50",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
            for i in json.load(urllib.request.urlopen(req, timeout=30)):
                if "價格警報" in i["title"] and "pull_request" not in i:
                    num = i["number"]; break
        except (urllib.error.URLError, OSError, ValueError):
            num = None
    if not num:
        try:
            req = urllib.request.Request(
                api + "/repos/kimifinal/price-monitor-pwa/issues",
                data=json.dumps({"title": "🔔 價格警報（自動）", "body": "由 refresh 排程自動投遞。"}).encode(),
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json",
                         "Content-Type": "application/json"}, method="POST")
            num = json.load(urllib.request.urlopen(req, timeout=30))["number"]
        except (urllib.error.URLError, OSError, ValueError):
            print("[alert:github-創建失敗]")
            return 0
    try:
        req = urllib.request.Request(
            f"{api}/repos/kimifinal/price-monitor-pwa/issues/{num}/comments",
            data=json.dumps({"body": body}).encode(),
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"}, method="POST")
        json.load(urllib.request.urlopen(req, timeout=30))
        return len(alerts)
    except (urllib.error.URLError, OSError, ValueError):
        print("[alert:github-投遞失敗]")
        return 0


def emit(alerts: list[dict], sink: str = "log", token: str = "") -> int:
    if not alerts:
        return 0
    if sink == "telegram":
        return emit_telegram(alerts)
    if sink == "github":
        return emit_github(alerts, token=token)
    return emit_log(alerts)
