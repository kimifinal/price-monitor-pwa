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

Golden rule (a hard AC of #2 / #9): **never fire on synthetic/fallback data**. An
SKU that has only a 14-day backfill (`current_is_real == False`) can never be
alerted, so an offline / fallback pipeline cannot produce false "buy now" shouts.
When a synthetic SKU *would* have tripped an alarm we LOG a skip note (never send).

Issue #9 (Telegram + GitHub delivery, CI-safe): sinks read their credentials from
the environment. The HTTP POST is isolated behind ONE mockable hook (`_http_post`)
so the suite is fully offline (zero real traffic) and a missing credential is a
graceful skip + `return 0` — it NEVER raises, fails the run, or logs the token.
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
# delivery
#
# Every live HTTP POST is isolated behind ONE overridable hook, `_http_post`, so
# the sinks are (a) fully offline-testable — a test injects a fake and the whole
# suite makes ZERO real network calls — and (b) CI-safe: with no credential a
# sink prints a skip note and returns 0; it never raises, never fails the run, and
# the credential is never echoed into a log/traceback. No new dependency: only
# stdlib `urllib` is used, so even an air-gapped runner can import this.
# --------------------------------------------------------------------------
BOT_API = "https://api.telegram.org/bot{token}/sendMessage"
GITHUB_API = "https://api.github.com"
ALERT_REPOSITORY = "kimifinal/price-monitor-pwa"
ALERT_ISSUE_TITLE = "🔔 價格警報"        # what the github sink appends its digest to
GITHUB_FIND_SUBSTR = "價格警報"          # substring used to FIND the alerting issue
PARSED_MODE = "Markdown"                 # per-alert telegram parse_mode


def _http_post(req, timeout: int = 10):
    """The single, mockable HTTP-POST hook.

    Default is stdlib `urllib.request.urlopen` (offline-safe: no real credential
    is ever constructed on this path in the test suite). A test injects its own
    fake via the `http_post=` kwarg on `emit_telegram` / `emit_github` / `emit` to
    assert the payload + parse_mode + dedup with NO real traffic. `req` is a
    fully-formed `urllib.request.Request`; a fake must behave like an `urlopen`
    return — a context-manager response exposing `.status` and, for the GitHub
    JSON path, `.read()`.
    """
    return urllib.request.urlopen(req, timeout=timeout)


# verdict -> leading emoji for the per-alert telegram message.
#   ✅  at the all-time floor                (the confirmed best time to buy)
#   📉  a genuine drop worth acting on       (a "good deal")
#   📈  otherwise / near the high            (not a falling price)
def _verdict_emoji(verdict: str) -> str:
    if verdict == "all_time_low":
        return "✅"
    if verdict == "good_deal":
        return "📉"
    return "📈"


def _is_all_time_low(a: dict) -> bool:
    """The all-time-low flag for the message: explicit `at_all_time_low`, else
    derived from the verdict (all_time_low ⇒ true)."""
    if "at_all_time_low" in a:
        return bool(a["at_all_time_low"])
    return a.get("verdict") == "all_time_low"


def alert_message(a: dict, parse_mode: str = PARSED_MODE) -> str:
    """Build the per-alert telegram text. Fields, IN ORDER (#9 spec):

        1. emoji by verdict      (✅ all-time floor / 📉 good deal / 📈 otherwise)
        2. '跌破'                  (the signal word — price broke below)
        3. item NAME
        4. current price
        5. verdict               (the SSOT code, e.g. all_time_low / good_deal)
        6. drop-pct-percent      (drop-from-high %)
        7. all-time-low          (是 / 否)
        8. deep-link             (the product URL)

    Pure + deterministic — the test pins the field order and every field's
    presence with no network. `parse_mode` is returned for symmetry with the
    JSON body it travels in; it does not alter the text.
    """
    verdict = a.get("verdict") or "unknown"
    emoji = _verdict_emoji(verdict)
    name = a.get("name") or a.get("sku") or "(unknown)"
    price = a.get("price")
    price_s = f"${price:,.0f}" if isinstance(price, (int, float)) else "$n/a"
    cur = a.get("currency") or "TWD"
    drop = a.get("drop_pct", 0.0)
    at_low = "是" if _is_all_time_low(a) else "否"
    link = (a.get("url") or "").strip() or "（無 link）"
    # The verdict emoji leads the line, then '跌破' then the name — i.e. the eight
    # #9 fields in order (emoji, 跌破, name, price, verdict, drop%, all-time-low,
    # deep-link) are laid out with a blank-paired separator so a test can pin the
    # order by substring search.
    return "  ".join([
        f"{emoji} 跌破 {name}",
        f"現價 {price_s} {cur}",
        f"verdict {verdict}（{a.get('label','')}）",
        f"▼ 跌幅 {drop}%",
        f"歷史最低 {at_low}",
        link,
    ])


def _legacy_telegram_send(text: str) -> bool:
    """Legacy target-price Telegram send (query-string style). Returns True when a
    real send happened, False when no creds are set — so the pipeline runs without
    them. Routed through `_http_post` (mockable); the token is NEVER printed."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat:
        return False                          # no creds -> not attempted
    base = "https://api.telegram.org/bot" + str(bot_token) + "/sendMessage"
    url = f"{base}?chat_id={urllib.parse.quote(str(chat))}&text=" + urllib.parse.quote(text)
    req = urllib.request.Request(url, method="POST", data=b"")
    try:
        with _http_post(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False                          # never leak the token (it is in url)


def send_telegram_alert(item, price) -> bool:
    """Legacy target-price Telegram sink. Kept for backwards compatibility
    (`main.py` still calls it). Same creds path as the verdict sink: returns True
    when a real send happened, False when no creds are set (no raise, no log of the
    token)."""
    name = getattr(item, "name", None)
    if name is None and isinstance(item, dict):
        name = item.get("name")
    name = name or str(item)
    target = getattr(item, "target", None)
    if target is None and isinstance(item, dict):
        target = item.get("target")
    suffix = f"（目標 ${target:.2f}）" if target else ""
    return _legacy_telegram_send(f"🔔 跌破目標價\n{name}: ${price:.2f}{suffix}")


# --------------------------------------------------------------------------
# verdict-based scanner (the #2 feature, on the price_verdict SSOT)
# --------------------------------------------------------------------------
STATE_PATH = os.path.join(os.path.dirname(__file__), "alerts_state.json")
DEFAULT_POLICY = {"alarm_verdicts": ("all_time_low", "good_deal")}


def _alert_verdicts(policy: Optional[dict]) -> set:
    return set((policy or DEFAULT_POLICY).get("alarm_verdicts", DEFAULT_POLICY["alarm_verdicts"]))


def alert_for(m: dict, policy: Optional[dict] = None,
              watchlist: Optional[list] = None,
              allow_synthetic: bool = False) -> Optional[dict]:
    """One SKU's metrics -> an alert dict when it trips an ALARM verdict, else None.

    Reuses `price_verdict` (the SSOT) so the "what counts as a good time to buy"
    rule is defined in exactly one place. Two hard guarantees:
      * returns None for an empty/sparse series, and
      * returns None for `current_is_real == False` — never fire on the synthetic
        backfill (unless `allow_synthetic`, which bypasses *only that* gate so a
        caller can DETECT + log a would-be alarm without delivering it; #9 skip-note).

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
    # Golden rule (#2/#9): NEVER deliver on a synthetic / only-backfill sku. The
    # `allow_synthetic` flag bypasses ONLY this gate so scan() can detect a
    # would-fire and emit a skip note — it never actually delivers it.
    if not allow_synthetic and not m.get("current_is_real"):
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
        "at_all_time_low": bool(m.get("at_all_time_low")),
    }


def alert_signature(a: dict) -> str:
    """Dedup key: one alert per (sku, verdict, day). A new verdict or a new day
    fires again; the same verdict on the same day is a no-op."""
    return f"{a['sku']}|{a['verdict']}|{a['as_of']}"


def scan(metrics_list: list[dict], state: Optional[dict] = None,
         policy: Optional[dict] = None,
         watchlist: Optional[list] = None,
         log_skipped: bool = False) -> tuple[list[dict], dict]:
    """Decide which SKUs should be alerted *now*, given a dedup `state`.

    `metrics_list` is the per-SKU metrics from `history.metrics` (already carrying
    `current_is_real`). Returns `(fresh_alerts, updated_state)`; `fresh_alerts`
    are the ones NOT already in `state`. The dedup (`alerts_state.json`) is what
    makes "notify once per event" hold — the SAME upstream gate every sink relies
    on, so a github batch comment fires once per event too (#9).

    The #4 GATE: when `watchlist` is passed, only skus IN the watchlist that meet
    their threshold are eligible (an unwatched sku or an unmet threshold is never
    alerted); `watchlist=[]` is the silent default (nothing fires); `None` disables
    the gate (legacy verdict-only, what the existing suite assumes).

    `log_skipped=True` also LOGS a one-line note for any synthetic / only-backfill
    sku that WOULD have alarmed through the full pipeline (#9 "log a skip note
    only") — it is NEVER among the returned `fresh` and is NEVER delivered.
    """
    state = dict(state or {})
    fresh: list[dict] = []
    skipped = 0
    for m in metrics_list:
        a = alert_for(m, policy, watchlist)
        if not a:
            # Would this have fired if it were real data? Log the skip, don't send.
            if log_skipped and m and not m.get("current_is_real"):
                probe = alert_for(m, policy, watchlist, allow_synthetic=True)
                if probe:
                    skipped += 1
            continue
        sig = alert_signature(a)
        sigs = state.setdefault(a["sku"], [])
        if sig in sigs:
            continue
        sigs.append(sig)
        a["sig"] = sig
        fresh.append(a)
    if log_skipped and skipped:
        print(f"[alert:skip] {skipped} synthetic/fallback sku(s) would have alerted "
              f"— NOT delivered (no false shouts)")
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


def emit_telegram(alerts: list[dict], http_post=None,
                  bot_token: Optional[str] = None,
                  chat_id: Optional[str] = None) -> int:
    """Send each alert to the Telegram bot (as a JSON `sendMessage`). Returns the
    number actually sent.

    CI-safe + no-secret (#9): reads `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from
    the environment (overridable via the `bot_token` / `chat_id` kwargs for tests).
    When EITHER is missing/empty it prints one skip note and returns 0 — it NEVER
    raises, fails the run, or prints the credential. The single POST is behind the
    overridable `http_post` hook so the suite asserts the JSON `{chat_id, text,
    parse_mode}` payload with zero real traffic. The per-alert `text` carries the
    eight #9 fields IN ORDER (see `alert_message`).
    """
    if http_post is None:
        http_post = _http_post
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat:
        # No creds / empty -> skip, fall back, and never touch the token.
        print("no telegram configured, skipping sink=telegram (fall back to log)")
        return 0
    sent = 0
    for a in alerts:
        text = alert_message(a)
        url = "https://api.telegram.org/bot" + str(bot_token) + "/sendMessage"
        payload = json.dumps(
            {"chat_id": str(chat), "text": text, "parse_mode": PARSED_MODE},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with http_post(req, timeout=10) as resp:
                sent += 1 if resp.status == 200 else 0
        except (urllib.error.URLError, OSError, ValueError):
            # Never echo url/token on failure — the credential lives in the URL.
            continue
    return sent


def _env_issue_number() -> Optional[int]:
    """The `ALERT_ISSUE` env var, when it pins the '🔔 價格警報' issue by number.
    Empty / non-numeric => None (fall through to find-by-title then create)."""
    raw = (os.environ.get("ALERT_ISSUE") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _github_find_issue(base: str, headers: dict, http_post):
    """List open issues, return the number of the first '🔔 價格警報' issue
    (skipping pull requests), else None. Never raises on a transport/parse error,
    so a transient API hiccup can't fail the scheduled job."""
    url = f"{base}?state=open&per_page=50"
    req = urllib.request.Request(url, headers=headers)
    try:
        with http_post(req, timeout=30) as resp:
            for i in json.loads(resp.read().decode("utf-8")):
                if i.get("pull_request"):
                    continue
                if GITHUB_FIND_SUBSTR in i.get("title", ""):
                    return i.get("number")
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError):
        return None
    return None


def _github_create_issue(base: str, headers: dict, http_post) -> Optional[int]:
    """Create the digest issue ONCE and return its number, else None on error."""
    data = json.dumps({
        "title": f"{ALERT_ISSUE_TITLE}（自動）",
        "body": "由 refresh 排程 + 警報掃描自動投遞的摘要 issue。",
    }).encode("utf-8")
    req = urllib.request.Request(base, data=data, method="POST", headers=headers)
    try:
        with http_post(req, timeout=30) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            return info.get("number")
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError):
        print("[alert:github] 創建 issue 失敗")
        return None


def emit_github(alerts: list[dict], token: str = "",
                issue_number: Optional[int] = None,
                http_post=None) -> int:
    """Append ONE deduped digest comment to the '🔔 價格警報' issue.

    Issue-number resolution (#9), in order: an explicit `issue_number`, else the
    `ALERT_ISSUE` env var, else FIND-by-title, else CREATE it. The whole path is
    behind the overridable `http_post` hook, so the suite mocks the GitHub API with
    zero real traffic.

    CI-safe + no-secret: the token comes from the Actions `GITHUB_TOKEN` (or the
    kwarg). When absent it SKIPS to the log sink (surfacing the alerts) instead of
    failing the run. "One batch comment, deduped per event" is guaranteed by the
    upstream `scan` / `alerts_state.json` dedup — this just posts the already
    deduped batch as a single comment.
    """
    if not alerts:
        return 0
    if http_post is None:
        http_post = _http_post
    resolved = token or os.environ.get("GITHUB_TOKEN", "")
    if issue_number is None:
        issue_number = _env_issue_number()
    lines = [f"- **{a['label']}** `{a['sku']}` {a['name']} "
             f"→ ${a['price']:,.0f}（{a['drop_pct']}% 距高點）" for a in alerts]
    body = f"#### 🔔 價格警報（{len(alerts)} 筆）\n" + "\n".join(lines)
    if not resolved:
        # CI-safe: no GITHUB_TOKEN => skip to the log sink, don't fail the run.
        print("[alert:github] no GITHUB_TOKEN — skipping sink=github (fall back to log)")
        return emit_log(alerts)
    headers = {"Authorization": f"token {resolved}",
               "Accept": "application/vnd.github+json",
               "Content-Type": "application/json"}
    base = f"{GITHUB_API}/repos/{ALERT_REPOSITORY}/issues"
    num = issue_number or _github_find_issue(base, headers, http_post)
    num = num or _github_create_issue(base, headers, http_post)
    if not num:
        print("[alert:github] 無法定位/建立 🔔 價格警報 issue — 略過投遞")
        return 0
    # One batch comment (the dedup that makes an event fire once is upstream).
    url = f"{base}/{num}/comments"
    data = json.dumps({"body": body}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with http_post(req, timeout=30) as resp:
            ok = resp.status == 200
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        ok = False
    if ok:
        return len(alerts)
    print("[alert:github] 投遞 comment 失敗（dedup 狀態仍已推進）")
    return 0


def emit(alerts: list[dict], sink: str = "log", token: str = "",
         http_post=None) -> int:
    """Dispatch to a sink. `log` (default) is always CI-green; `telegram` reads its
    creds from the env (the `token` arg is the GITHUB_TOKEN and is IGNORED by the
    telegram sink); `github` uses the Actions GITHUB_TOKEN and the `http_post`
    hook. Returns the number actually delivered."""
    if not alerts:
        return 0
    if sink == "telegram":
        # bot chat comes from the env; the `token` arg is the GITHUB_TOKEN.
        return emit_telegram(alerts, http_post=http_post)
    if sink == "github":
        return emit_github(alerts, token=token, http_post=http_post)
    return emit_log(alerts)
