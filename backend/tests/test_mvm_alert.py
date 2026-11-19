"""B3 (Tier B of #35) — offline tests for MVM 警報 (mvm_alert).

AC coverage (ALL offline: `log` sink + an injected fake `http_post`, shared
`alerts_state` to prove the dedup — ZERO real network, ZERO real vision):

  * NEW TAB    — a newly-appeared MVM 檔期 (B1 `detect_new_tabs`) fires a
                 `new_mvm_tab` alert (distinct verdict + 🆕 label).
  * PRICE DROP — a MVM price fall fires a `price_drop` alert, REUSING Tier A
                 `detect_change` (promo fell vs the previous snapshot).
  * SILENCE    — no new tab AND no drop -> no alert, nothing delivered.
  * FALLBACK   — no previous snapshot -> NO crash AND NO false "price dropped"
                 shout: a fresh snapshot only reveals `new_item`, which MVM does
                 not alert on — so the golden rule (never fire on non-real /
                 fallback data) holds here too.
  * DEDUP + SINK — `scan_mvm` dedups through `alerts.alert_signature` +
                 `detect_change.scan_events` over ONE shared `state`, and routes
                 delivery through `alerts.emit` (log / telegram).  A `new_mvm_tab`
                 signature never collides with a `price_drop` one.  Nothing in
                 this module re-implements dedup or the sink — that surface lives
                 in `alerts.py` / `detect_change.py` (Tier A), which mvm_alert wraps.
"""
import json
from pathlib import Path

import mvm_alert as A
import mvm_detect
import mvm_vision as M
import alerts

MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "data"
                       / "costco_mvm" / "manifest.json").read_text(encoding="utf-8"))

# the 6 tracked tab urls, exactly as B1 derives them (the "known" baseline).
KNOWN = [mvm_detect.tab_url(MANIFEST, t["tab_id"]) for t in MANIFEST["tabs"]]
# a 7th url B1 has never seen -> a brand-new MVM 檔期.
NEW_URL = "https://www.costco.com.tw/content/fy27p5-mvm2-w1"
NEW_TAB_ID = "fy27p5-mvm2-w1"

# a one-item prev catalog: sku 100 stable at promo 1000.
PREV = {"fy27p3-mvm2-w1": [{"sku": 100, "name": "keep", "orig": 1000, "promo": 1000}]}
# a price-drop cur catalog: same sku, promo fell 1000 -> 800.
DROP_CUR = {"fy27p3-mvm2-w1": [{"sku": 100, "name": "keep", "orig": 1000, "promo": 800}]}
# a fresh snapshot (only a brand-new sku, vs nothing) -> just a new_item.
FRESH = {"fy27p3-mvm2-w1": [{"sku": 777, "name": "全新商品", "orig": 5, "promo": 4}]}


# --------------------------- AC: a new MVM tab fires an alert ---------------------------

def test_new_tab_fires_a_new_mvm_tab_alert():
    out = A.new_tab_alerts(KNOWN + [NEW_URL], MANIFEST, as_of="2026-11-18")
    assert len(out) == 1
    a = out[0]
    assert a["verdict"] == A.NEW_MVMTAB_VERDICT == "new_mvm_tab"
    assert a["type"] == "new_mvm_tab"
    assert a["sku"] == NEW_TAB_ID                 # the tab_id IS the dedup identity
    assert a["tab_id"] == NEW_TAB_ID
    assert a["label"] == A.NEW_MVMTAB_LABEL == "🆕 新 MVM 檔期"
    assert a["real"] is True
    assert a["url"].endswith("/" + NEW_TAB_ID)    # reconstructed for a not-in-manifest tab
    assert a["as_of"] == "2026-11-18"


def test_new_tab_alert_shape_is_alerts_emit_compatible():
    # reuse proof: the dict has EVERY field alerts.alert_signature / emit read.
    a = A.mvm_new_tab_alert(NEW_TAB_ID, KNOWN + [NEW_URL], MANIFEST, as_of="2026-11-18")
    # alert_signature only needs sku / verdict / as_of — exercise it directly.
    sig = alerts.alert_signature(a)
    assert sig == f"{NEW_TAB_ID}|new_mvm_tab|2026-11-18"
    # emit_log (the always-green sink) consumes the dict without a KeyError.
    assert alerts.emit_log([a]) == 1
    for field in ("sku", "verdict", "label", "as_of", "name", "price",
                  "drop_pct", "url", "currency", "at_all_time_low", "type"):
        assert field in a, f"missing alerts field: {field}"


def test_silent_when_only_known_tabs_observed():
    # golden AC: feed only the manifest's own urls -> no new tab, no false alarm.
    out = A.new_tab_alerts(KNOWN, MANIFEST, as_of="2026-11-18")
    assert out == []
    assert A.new_tab_alerts([], MANIFEST) == []
    assert A.new_tab_alerts(None, MANIFEST) == []         # degrade, never crash
    assert A.new_tab_alerts(KNOWN, None) == []            # no manifest -> no baseline


# --------------------------- AC: a MVM price drop fires an alert ---------------------------

def test_price_drop_fires_a_price_drop_alert_reusing_tier_a():
    out = A.price_drop_alerts(PREV, DROP_CUR, as_of="2026-11-17")
    assert len(out) == 1
    a = out[0]
    assert a["verdict"] == "price_drop"
    assert a["type"] == "price_drop"
    assert a["label"] == "📉 降價"
    assert a["sku"] == "100"
    assert a["drop_pct"] == 20.0          # 1000 -> 800 == 20% off
    assert a["price"] == 800
    assert a["currency"] == "TWD"
    assert a["as_of"] == "2026-11-17"


def test_price_drop_accepts_the_p4_catalog_shape_too():
    # mvm_alert flattens BOTH {tab_id: [products]} and p4 {tabs:[{products}]}
    prev_p4 = {"tabs": [{"tab_id": "fy27p3-mvm2-w1",
                         "products": [{"sku": 100, "name": "keep", "orig": 1000, "promo": 1000}]}]}
    cur_p4 = {"tabs": [{"tab_id": "fy27p3-mvm2-w1",
                        "products": [{"sku": 100, "name": "keep", "orig": 1000, "promo": 850}]}]}
    out = A.price_drop_alerts(prev_p4, cur_p4, as_of="2026-11-17")
    assert len(out) == 1
    assert out[0]["verdict"] == "price_drop"
    assert out[0]["drop_pct"] == 15.0     # 1000 -> 850 == 15% off


def test_no_price_drop_when_unchanged():
    # sku present at the SAME promo in both snapshots -> no drop event (silence).
    assert A.price_drop_alerts(PREV, PREV, as_of="2026-11-17") == []
    assert A.price_drop_alerts(None, DROP_CUR, as_of="2026-11-17") == []   # no prev -> no diff


# --------------------------- AC: silence when nothing changed ---------------------------

def test_scan_mvm_is_silent_when_nothing_changed():
    res = A.scan_mvm(PREV, PREV, KNOWN, MANIFEST, as_of="2026-11-17",
                     state={}, sink="log")
    assert res["alerts"] == []
    assert res["new_tab_alerts"] == []
    assert res["price_drop_alerts"] == []
    assert res["delivered"] == 0
    assert res["new_tabs"] == []
    assert res["sources"] == "mvm-vision(tier-b)"
    # the documented result shape is intact
    for key in ("new_tabs", "new_tab_alerts", "price_drop_alerts",
                "alerts", "delivered", "state", "sources"):
        assert key in res


# --------------------------- dedup + sink: reuse the Tier A surface ---------------------------

def test_scan_mvm_new_tab_delivers_once_then_dedups():
    # first scan fires the new tab; the SECOND scan, given the SAME (forwarded)
    # state, dedups it -> 0 delivered.  This is alerts.alert_signature reuse.
    state = {}
    r1 = A.scan_mvm(None, {}, KNOWN + [NEW_URL], MANIFEST,
                    as_of="2026-11-17", state=dict(state), sink="log")
    assert len(r1["new_tab_alerts"]) == 1
    assert r1["delivered"] == 1
    r2 = A.scan_mvm(None, {}, KNOWN + [NEW_URL], MANIFEST,
                    as_of="2026-11-17", state=r1["state"], sink="log")
    assert r2["alerts"] == []           # deduped via the shared state
    assert r2["delivered"] == 0


def test_new_tab_and_price_drop_share_state_with_distinct_signatures():
    # both signals in ONE scan -> BOTH alert, with two DIFFERENT dedup signatures
    # (new_mvm_tab's tab_id key vs price_drop's sku key never collide).
    r = A.scan_mvm(PREV, DROP_CUR, KNOWN + [NEW_URL], MANIFEST,
                   as_of="2026-11-19", state={}, sink="log")
    assert len(r["alerts"]) == 2
    sigs = {a["sig"] for a in r["alerts"]}
    assert len(sigs) == 2                                  # distinct dedup keys
    verdicts = {a["verdict"] for a in r["alerts"]}
    assert verdicts == {"new_mvm_tab", "price_drop"}
    assert r["delivered"] == 2


def test_price_drop_dedup_reused_across_runs_via_shared_state():
    s = {}
    d1 = A.scan_mvm(PREV, DROP_CUR, KNOWN, MANIFEST, as_of="2026-11-17",
                    state=dict(s), sink="log")
    d2 = A.scan_mvm(PREV, DROP_CUR, KNOWN, MANIFEST, as_of="2026-11-17",
                    state=d1["state"], sink="log")
    assert len(d1["price_drop_alerts"]) == 1
    assert d1["delivered"] == 1
    assert d2["delivered"] == 0                  # the drop shouts only once


def test_sink_routing_through_alerts_emit_with_fake_post(monkeypatch):
    # reuse proof for the SINK: mvm_alert routes delivery through alerts.emit
    # (-> emit_telegram); a fake http_post makes this zero-network + CI-safe.
    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    calls = []

    def fake_post(req, timeout=10):
        calls.append(req)
        return _Resp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
    # a genuine price_drop needs the sku in BOTH snapshots at different promos.
    r = A.scan_mvm(PREV, DROP_CUR, KNOWN, MANIFEST, as_of="2026-11-17",
                   state={}, sink="telegram", http_post=fake_post)
    assert r["delivered"] == 1                  # 1 drop routed through alerts.emit
    assert len(calls) == 1                     # exactly one POST reached the sink
    url = (calls[0].get_full_url() if hasattr(calls[0], "get_full_url")
           else calls[0].full_url)
    assert str(url).endswith("/sendMessage")   # it really is the telegram sink


# --------------------------- AC: a fallback (no snapshot) never false-reports ---------------------------

def test_fallback_no_prev_does_not_crash_or_false_alert():
    # no previous snapshot: the fresh catalog only reveals a new_item, which MVM
    # does NOT alert on -> no "price dropped" shout, and no crash.
    res = A.scan_mvm(None, FRESH, KNOWN, MANIFEST, as_of="2026-11-17",
                     state={}, sink="log", log_skipped=True)
    assert res["alerts"] == []
    assert res["price_drop_alerts"] == []           # new_item is filtered out
    assert res["delivered"] == 0
    assert res["new_tabs"] == []


def test_fallback_everything_empty_is_silent_and_crashfree():
    # total fallback: no manifest, no catalogs, no observed -> nothing, no crash.
    res = A.scan_mvm(None, None, None, None, as_of="2026-11-17",
                     state={}, sink="log")
    assert res["alerts"] == []
    assert res["delivered"] == 0
    assert A.price_drop_alerts(None, None) == []
    assert A.drops_as_events(None, None) == []


def test_run_mvm_alert_is_offline_returns_int_and_dedups(tmp_path):
    # run_mvm_alert threads a durable state_path through alerts.save/load_state.
    sp = str(tmp_path / "mvm_alert_state.json")
    d1 = A.run_mvm_alert(PREV, DROP_CUR, KNOWN, MANIFEST,
                         as_of="2026-11-17", sink="log", state_path=sp)
    assert isinstance(d1, int)
    assert d1 == 1                                  # 1 price_drop delivered
    d2 = A.run_mvm_alert(PREV, DROP_CUR, KNOWN, MANIFEST,
                         as_of="2026-11-17", sink="log", state_path=sp)
    assert d2 == 0                                  # deduped on reload
    # the state persisted to disk (the dedup SSOT survives the run)
    assert (tmp_path / "mvm_alert_state.json").exists()
    # and no state_path means no file write, still fine
    assert A.run_mvm_alert(None, FRESH, KNOWN, MANIFEST, as_of="2026-11-17",
                           sink="log", state_path=None) == 0


def test_verdicts_are_module_constants_reused():
    # the verdicts mvm_alert emits are stable, distinct constants (so dedup can
    # never collapse a new-tab alert into a price-drop one).
    assert A.NEW_MVMTAB_VERDICT == "new_mvm_tab"
    assert A.DROP_VERDICT == "price_drop"
    assert A.NEW_MVMTAB_VERDICT != A.DROP_VERDICT
    assert A.NEW_MVMTAB_VERDICT != "all_time_low" and A.NEW_MVMTAB_VERDICT != "good_deal"
