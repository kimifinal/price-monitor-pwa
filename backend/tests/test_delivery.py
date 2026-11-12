"""Issue #9 — delivery path: telegram + github sinks, dedup, no-leak.

Every assertion here is OFFLINE and credential-free. The HTTP POST sits behind
`alerts._http_post`, which the tests replace with fakes — so the whole suite makes
ZERO real network calls and contains NO real token/chat-id anywhere. Real
credentials come only from the environment (as the live sink reads them); the tests
set short, non-secret placeholders or mock the HTTP layer outright.
"""
import json
import re
import os

import alerts
from alerts import (
    alert_message,
    emit,
    emit_telegram,
    emit_github,
    scan,
    _verdict_emoji,
    _env_issue_number,
)


# --------------------------------------------------------------------------- #
# shared fakes — a stand-in for an urlopen() return + a recordable POST hook
# --------------------------------------------------------------------------- #
class _Resp:
    """A stand-in for an `urlopen()` return: a context manager exposing `.status`
    and, for the GitHub JSON path, `.read()`."""

    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body if isinstance(body, (bytes, bytearray)) \
            else json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GitHubFake:
    """A recordable, route-by-URL fake of the GitHub REST calls emit_github makes.

    `issue_number`: when set, the 'list open issues' call RETURNs that issue so the
    find-by-title branch hits it (no create); when None, the list is empty so the
    create branch runs. Captures every POST so a test can assert the batch-comment
    body + that each event posts exactly once (the upstream dedup guarantee)."""

    def __init__(self, issue_number=None):
        self.list_issue = ({"number": issue_number,
                            "title": "🔔 價格警報（自動）"}
                           if issue_number else None)
        self.created = 0
        self.comments = []      # list of (issue_number, body_dict)
        self.calls = 0

    def __call__(self, req, timeout=30):
        self.calls += 1
        url = req.full_url
        method = req.get_method()
        # 1) list open issues (the find-by-title step)
        if "state=open" in url:
            body = [self.list_issue] if self.list_issue else []
            return _Resp(200, json.dumps(body).encode("utf-8"))
        # 2) create the issue: a POST to .../issues with no query / no /comments
        if method == "POST" and url.endswith("/issues"):
            self.created += 1
            return _Resp(200, json.dumps({"number": 777}).encode("utf-8"))
        # 3) the single batch comment: POST .../issues/{n}/comments
        if "/comments" in url:
            m = re.search(r"/issues/(\d+)/comments", url)
            issue = int(m.group(1)) if m else -1
            self.comments.append((issue, json.loads(req.data or b"{}")))
            return _Resp(200, json.dumps({"id": 1}).encode("utf-8"))
        return _Resp(200, b"{}")


def M(**over):
    """A real, non-synthetic metrics dict that yields an all_time_low alert."""
    base = dict(
        sku="149699", name="ANKER A2674 67W", tag="3C", points=14,
        current=800.0, low=800.0, high=1000.0, drop_pct_from_high=20.0,
        at_all_time_low=True, current_is_real=True, currency="TWD",
        url="https://www.costco.com/p/149699", last_seen="2026-11-11T00:00:00",
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# (a) sink=telegram: the POST carries {chat_id, text, parse_mode}; the per-alert
#     text has the eight #9 fields IN ORDER; and an event fires exactly ONCE
# --------------------------------------------------------------------------- #
def test_telegram_message_payload_order_and_parse_mode(monkeypatch):
    # creds come from the env, exactly as the live sink reads them; the POST is faked
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    captured = []
    def fake_post(req, timeout=10):
        captured.append(json.loads(req.data or b"{}"))
        return _Resp(200)

    fresh, state = scan([M()], state={})
    assert len(fresh) == 1

    sent = emit_telegram(fresh, http_post=fake_post)
    assert sent == 1
    assert len(captured) == 1, "one alert -> exactly one sendMessage POST"

    payload = captured[0]
    # the three required JSON envelope fields
    assert payload["chat_id"] == "42"
    assert payload["parse_mode"] == "Markdown"
    text = payload["text"]
    # the eight per-alert fields, in order, each present and monotonically ordered
    markers = [
        "✅",                      # 1. verdict emoji
        "跌破",                    # 2. the signal word
        "ANKER A2674 67W",        # 3. item name
        "現價 $800 TWD",           # 4. current price
        "verdict all_time_low",   # 5. the verdict (from the SSOT)
        "▼ 跌幅 20.0%",           # 6. drop-pct-percent
        "歷史最低 是",             # 7. all-time-low (是/否)
        "https://www.costco.com/p/149699",  # 8. deep-link
    ]
    positions = [text.find(mk) for mk in markers]
    assert all(p >= 0 for p in positions), f"missing field(s): {list(zip(markers, positions))}"
    assert positions == sorted(positions), f"fields out of order: {list(zip(markers, positions))}"


def test_telegram_fires_once_per_event(monkeypatch):
    """The dedup state makes 'notify once per event' true for telegram too: a
    re-scan of the same event is empty, so a second emit posts NOTHING."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    calls = []
    def first(req, timeout=10):
        calls.append(req)
        return _Resp(200)

    fresh, state = scan([M()], state={})
    assert emit_telegram(fresh, http_post=first) == 1
    assert len(calls) == 1                       # sent exactly once

    # a re-scan with the SAME state yields no new alert
    again, _ = scan([M()], state=state)
    assert again == []

    # a second emit of the (now empty) fresh set must NOT touch the network:
    def boom(req, timeout=10):
        raise AssertionError("deduped event must not be re-sent")
    assert emit_telegram(again, http_post=boom) == 0   # no POST happened


# --------------------------------------------------------------------------- #
# (b) missing token -> skip, return 0, and NO network attempt
# --------------------------------------------------------------------------- #
def test_telegram_missing_token_skips_no_network(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    attempts = []
    def guard(req, timeout=10):
        attempts.append(req)             # recorded on ANY real attempt
        return _Resp(200)

    alerts_list = scan([M()], state={})[0]
    assert alerts_list                   # there IS a real alert to try to send
    n = emit_telegram(alerts_list, http_post=guard)

    assert n == 0                                    # skipped, returns 0
    assert attempts == []                            # no network attempt at all
    out = capsys.readouterr().out
    assert "no telegram configured, skipping sink=telegram (fall back to log)" in out

    # also: an empty chat id with a token is treated the same (must not send)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0")
    attempts.clear()
    assert emit_telegram(alerts_list, http_post=guard) == 0
    assert attempts == []


def test_telegram_empty_env_treated_as_missing(monkeypatch):
    """An empty-string credential is exactly the same as a missing one: skip + 0."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    def guard(req, timeout=10):
        raise AssertionError("must not POST with empty creds")
    assert emit_telegram(scan([M()], state={})[0], http_post=guard) == 0


# --------------------------------------------------------------------------- #
# (c) sink=github: get-or-create the '🔔 價格警報' issue + one deduped batch comment
# --------------------------------------------------------------------------- #
def test_github_find_existing_issue_by_title(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")      # short placeholder, not a literal key
    monkeypatch.delenv("ALERT_ISSUE", raising=False)
    gh = GitHubFake(issue_number=7)                   # find-by-title returns #7

    a = {"sku": "149699", "name": "ANKER 67W", "verdict": "all_time_low",
         "label": "歷史最低 👍", "drop_pct": 20.0, "price": 800, "currency": "TWD",
         "url": "https://www.costco.com/p/149699"}
    n = emit_github([a], http_post=gh)
    assert n == 1
    assert gh.created == 0                            # found it -> did NOT create
    assert len(gh.comments) == 1                      # one batch comment
    assert gh.comments[0][0] == 7                     # commented on the found issue
    assert "ANKER 67W" in gh.comments[0][1]["body"]   # the digest carries the alert


def test_github_create_issue_when_none(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    monkeypatch.delenv("ALERT_ISSUE", raising=False)
    gh = GitHubFake(issue_number=None)                # find miss -> create path
    a = {"sku": "3062725", "name": "BOSE Bar", "verdict": "good_deal",
         "label": "較近低點 ▼", "drop_pct": 16.0, "price": 900, "currency": "TWD",
         "url": "https://www.costco.com/p/3062725"}
    n = emit_github([a], http_post=gh)
    assert n == 1
    assert gh.created == 1                # created the issue exactly once
    assert len(gh.comments) == 1          # ... then one batch comment
    assert gh.comments[0][0] == 777       # commented on the just-created issue


def test_github_env_issue_number_bypasses_find_and_create(monkeypatch):
    """ALERT_ISSUE pins the issue number: no find, no create — just the comment."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    monkeypatch.setenv("ALERT_ISSUE", "999")
    gh = GitHubFake()
    a = {"sku": "161520", "name": "Samsung 55", "verdict": "all_time_low",
         "label": "歷史最低 👍", "drop_pct": 15.0, "price": 18000, "currency": "TWD",
         "url": "https://www.costco.com/p/161520"}
    n = emit_github([a], http_post=gh)
    assert n == 1
    assert gh.created == 0
    assert gh.comments[0][0] == 999       # used the env-pinned number


def test_github_no_token_skips_to_log(monkeypatch, capsys):
    """No GITHUB_TOKEN -> skip to the log sink, never fail, never touch the net."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ALERT_ISSUE", raising=False)
    gh = GitHubFake()
    a = {"sku": "149699", "name": "ANKER", "verdict": "all_time_low",
         "label": "歷史最低 👍", "drop_pct": 20.0, "price": 800, "currency": "TWD",
         "url": "https://www.costco.com/p/149699"}
    n = emit_github([a], http_post=gh)
    assert n == 1                          # emit_log returned the count
    assert gh.calls == 0                   # zero GitHub requests
    assert "no GITHUB_TOKEN" in capsys.readouterr().out   # the fallback note


def test_github_each_event_fires_once(monkeypatch):
    """Upstream dedup (alerts_state.json) => one batch comment per event, even
    across re-scans."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    monkeypatch.delenv("ALERT_ISSUE", raising=False)
    gh = GitHubFake(issue_number=None)

    fresh, state = scan([M()], state={})
    assert len(fresh) == 1
    assert emit_github(fresh, http_post=gh) == 1
    assert gh.created == 1 and len(gh.comments) == 1

    again, _ = scan([M()], state=state)      # same event -> deduped to nothing
    assert again == []
    assert emit_github(again, http_post=gh) == 0
    assert gh.created == 1 and len(gh.comments) == 1   # still exactly one issue + one comment


# --------------------------------------------------------------------------- #
# (e) a synthetic / only-backfill SKU NEVER gets delivered (log a skip note only)
# --------------------------------------------------------------------------- #
def test_synthetic_only_backfill_never_delivered(monkeypatch, capsys):
    """current_is_real == False => never among fresh, never posted anywhere; the
    only observability is a skip note."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    synth = M(sku="synth", current_is_real=False)   # at all-time low but only backfilled

    # github sink
    gh = GitHubFake(issue_number=7)
    fresh, state = scan([synth], state={}, log_skipped=True)
    out = capsys.readouterr().out
    assert fresh == []                         # synthetic is never a fresh alert
    assert "skip" in out                       # ... a skip note was logged
    assert emit_github(fresh, http_post=gh) == 0
    assert gh.calls == 0                       # nothing reached the network

    # telegram sink
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    seen = []
    fake = lambda req, timeout=10: seen.append(req) or _Resp(200)
    assert emit_telegram(scan([synth], state={}, log_skipped=True)[0], http_post=fake) == 0
    assert seen == []


# --------------------------------------------------------------------------- #
# the emitter / dispatch
# --------------------------------------------------------------------------- #
def test_emit_dispatch_log_is_default_and_green(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    a = alert_for_stub()
    assert emit(a, sink="log") == 1            # log always works, no creds needed
    assert emit(a, sink="telegram") == 0       # telegram with no creds -> skip + 0
    assert emit(a, sink="github") == 1         # github with no token -> log fallback + count
    assert emit([], sink="log") == 0           # nothing to emit


def alert_for_stub():
    return [{"sku": "1", "name": "X", "verdict": "all_time_low", "label": "歷史最低 👍",
             "drop_pct": 20.0, "price": 800, "currency": "TWD",
             "url": "https://www.costco.com/p/1"}]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def test_emoji_by_verdict():
    assert _verdict_emoji("all_time_low") == "✅"
    assert _verdict_emoji("good_deal") == "📉"
    assert _verdict_emoji("near_high") == "📈"
    assert _verdict_emoji("unknown") == "📈"


def test_alert_message_field_order():
    a = {"verdict": "all_time_low", "label": "歷史最低 👍", "name": "ANKER A2674 67W",
         "price": 800, "currency": "TWD", "drop_pct": 20.0,
         "url": "https://www.costco.com/p/149699", "at_all_time_low": True}
    t = alert_message(a)
    markers = ["✅", "跌破", "ANKER A2674 67W", "現價 $800 TWD", "verdict all_time_low",
               "▼ 跌幅 20.0%", "歷史最低 是", "https://www.costco.com/p/149699"]
    pos = [t.find(mk) for mk in markers]
    assert all(p >= 0 for p in pos)
    assert pos == sorted(pos)


def test_env_issue_number_parsing(monkeypatch):
    monkeypatch.delenv("ALERT_ISSUE", raising=False)
    assert _env_issue_number() is None
    monkeypatch.setenv("ALERT_ISSUE", "42")
    assert _env_issue_number() == 42
    monkeypatch.setenv("ALERT_ISSUE", "not-a-number")
    assert _env_issue_number() is None
    monkeypatch.setenv("ALERT_ISSUE", "  99  ")
    assert _env_issue_number() == 99
