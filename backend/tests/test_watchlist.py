"""Tests for the #4 個人化 watchlist gate.

These pin the ACs the issue demands, all offline + deterministic (no network,
no creds):

  * a WATCHED sku that MEETS its threshold -> an alert fires;
  * a NON-watchlisted sku never alerts, even at an all-time low;
  * an EMPTY watchlist is silent (no alerts — the safe default);
  * a threshold that is MET vs one that is UNMET (target price + min drop%);
  * DECOUPLING: toggling the watchlist (add / remove / save) never mutates
    the time-series SSOT `history_data.json`;
  * the verdict is still sourced from `models.price_verdict` (never re-implemented),
    the watchlist only decides *which* verdicts are allowed through.

The trigger reuses the ONE rule (price_verdict) — the watchlist is only the gate.
"""
import json
import os

import alerts
import models
import watchlist


# A metrics dict shaped exactly like history.metrics() output (current_is_real True,
# at an all-time low). One field, `m`, to drive every branch below.
def M(sku="1", **over):
    base = dict(sku=str(sku), name="Widget", tag="3C", points=14,
                current=80.0, low=80.0, high=100.0,
                drop_pct_from_high=20.0, at_all_time_low=True,
                current_is_real=True, last_seen="2026-11-11T00:00:00")
    base.update(over)
    return base


# ---------------- watchlist.py: the SSOT itself ----------------

def test_load_missing_returns_empty(tmp_path):
    # absent watchlist => empty => silent, never raises (offline-safe)
    assert watchlist.load(str(tmp_path / "nope.json")) == []
    assert watchlist.skus([]) == []


def test_load_corrupt_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json ", encoding="utf-8")
    assert watchlist.load(str(p)) == []
    (tmp_path / "obj.json").write_text('{"a": 1}', encoding="utf-8")
    assert watchlist.load(str(tmp_path / "obj.json")) == []    # not a list -> []


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "wl.json"
    entries = [
        {"sku": "1", "name": "A", "threshold": {"target": 100}},
        {"sku": "2", "name": "B", "threshold": {"min_drop_pct": 15}},
    ]
    assert watchlist.save(entries, p) == 2
    reloaded = watchlist.load(p)
    assert {e["sku"] for e in reloaded} == {"1", "2"}


def test_save_is_deterministic_and_idempotent(tmp_path):
    # re-saving the same entries yields a byte-identical file (no churn)
    p = tmp_path / "wl.json"
    entries = [{"sku": "3", "name": "C", "threshold": {"target": 5, "min_drop_pct": 10}}]
    watchlist.save(entries, p)
    first = p.read_text(encoding="utf-8")
    watchlist.save(watchlist.load(p), p)
    assert p.read_text(encoding="utf-8") == first


def test_save_drops_skuless_junk(tmp_path):
    p = tmp_path / "wl.json"
    n = watchlist.save([{"sku": "1"}, {"name": "no sku"}, "junk", 7, {"sku": None}], p)
    assert n == 1
    assert watchlist.load(p) == [{"sku": "1"}]


def test_committed_demo_watchlist_is_watchlist(tmp_path):
    # the real SSOT file loads as a non-empty watchlist of {sku,name,threshold}
    wl = watchlist.load(watchlist.WATCHLIST_PATH)
    assert len(wl) >= 1
    for e in wl:
        assert "sku" in e and e.get("sku") is not None
        th = e.get("threshold") or {}
        assert all(k in ("target", "min_drop_pct") for k in th)


def test_default_watchlist_is_the_six_suggested_costco_items(tmp_path):
    """#14: the committed default watchlist is the 6 SKU list the user approved
    (SKU + name + target, all from the real 30-SKU costco snapshot). A future
    edit that drops or moves an item is caught here — a guard on the guard."""
    EXPECTED = [
        ("149699", "ANKER A2674 336 GaN 67W 急速充電器 2入組", 1069),
        ("153876", "JBL Live 670NC 耳罩式降噪藍牙耳機", 1899),
        ("161367", "Soundcore AeroClip 開放式藍牙耳夾耳機", 2079),
        ("153526", "飛利浦 55吋 4K QLED Google TV 顯示器 55PQT8530/96", 12599),
        ("156974", "iClever BTH18 炫光無線兒童耳機", 849),
        ("162427", "Hawk 360° 旋轉升降螢幕架 附抽屜", 669),
    ]
    wl = watchlist.load(watchlist.WATCHLIST_PATH)
    by_sku = {str(e["sku"]): e for e in wl}
    # exactly the 6 SKUs — no more, no fewer
    assert set(by_sku) == {s for s, _, _ in EXPECTED}
    for sku, name, target in EXPECTED:
        e = by_sku[sku]
        assert e["name"] == name
        assert e["threshold"]["target"] == target


# ---------------- threshold_met: target price vs min drop% ----------------

def test_threshold_met_target_price_uses_should_alert():
    # target price reuses models.should_alert (price <= target)
    m = M(sku="1", current=80.0)
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {"target": 100}}) is True
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {"target": 75}}) is False
    # and it literally IS should_alert
    assert "target" and models.should_alert(80.0, 100) is True


def test_threshold_met_min_drop_pct_uses_drop_from_high():
    m = M(sku="1", drop_pct_from_high=20.0)
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {"min_drop_pct": 15}}) is True
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {"min_drop_pct": 30}}) is False


def test_threshold_met_both_fields_are_AND():
    m = M(sku="1", current=80.0, drop_pct_from_high=20.0)
    # both satisfied
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {"target": 100, "min_drop_pct": 15}})
    # price fails, drop ok -> unmet (AND)
    assert not watchlist.threshold_met(m, {"sku": "1", "threshold": {"target": 75, "min_drop_pct": 15}})
    # price ok, drop fails -> unmet (AND)
    assert not watchlist.threshold_met(m, {"sku": "1", "threshold": {"target": 100, "min_drop_pct": 30}})


def test_threshold_met_no_gate_when_absent():
    m = M(sku="1")
    assert watchlist.threshold_met(m, {"sku": "1"}) is True
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": {}}) is True


def test_threshold_met_missing_data_is_not_met():
    # a target with no current => not met; a min-drop with no drop => not met
    assert watchlist.threshold_met({"sku": "1"}, {"sku": "1", "threshold": {"target": 100}}) is False
    assert watchlist.threshold_met({"sku": "1"}, {"sku": "1", "threshold": {"min_drop_pct": 10}}) is False


def test_threshold_met_tolerates_junk_entry():
    m = M(sku="1")
    assert watchlist.threshold_met(m, None) is True
    assert watchlist.threshold_met(m, "not a dict") is True
    assert watchlist.threshold_met(m, {"sku": "1", "threshold": "garbage"}) is True


# ---------------- find_entry: string-match skus ----------------

def test_find_entry_matches_by_sku_as_string():
    wl = [{"sku": 149699, "threshold": {"target": 1000}}, {"sku": "999", "threshold": {}}]
    assert watchlist.find_entry(M(sku="149699"), wl) is not None   # int vs str agree
    assert watchlist.find_entry(M(sku="888"), wl) is None
    assert watchlist.find_entry(M(sku="149699"), []) is None


# ==================== THE GATE (scan / alert_for) ====================

# AC: a watchlisted sku that METS its threshold -> an alert fires.
def test_watchlisted_threshold_met_fires():
    wl = [{"sku": "1", "name": "A", "threshold": {"target": 100}}]
    a = alerts.alert_for(M(sku="1", current=80.0, drop_pct_from_high=0.0), watchlist=wl)
    assert a is not None
    assert a["verdict"] == "all_time_low"      # the verdict still comes from price_verdict
    assert a["threshold"] == {"target": 100}


def test_watchlisted_by_drop_fires():
    wl = [{"sku": "1", "threshold": {"min_drop_pct": 15}}]
    a = alerts.alert_for(M(sku="1", at_all_time_low=False, drop_pct_from_high=20.0,
                           current=80.0, high=100.0), watchlist=wl)
    assert a is not None and a["verdict"] == "good_deal"


# AC: a NON-watchlisted sku NEVER alerts, even at an all-time low.
def test_non_watchlisted_never_alerts_even_at_all_time_low():
    wl = [{"sku": "2", "threshold": {"target": 100}}]   # sku 1 is NOT watched
    assert alerts.alert_for(M(sku="1", at_all_time_low=True), watchlist=wl) is None
    # scan over a list containing the unwatched all-time-low sku => no alert
    fresh, _ = alerts.scan([M(sku="1", at_all_time_low=True)], state={}, watchlist=wl)
    assert fresh == []


# AC: an EMPTY watchlist => NO alerts (the silent default).
def test_empty_watchlist_is_silent():
    assert alerts.alert_for(M(), watchlist=[]) is None
    fresh, _ = alerts.scan([M(sku="1"), M(sku="2")], state={}, watchlist=[])
    assert fresh == []


# AC: threshold MET vs UNMET.
def test_threshold_unmet_blocks_alert():
    wl = [{"sku": "1", "threshold": {"target": 50}}]   # current 80 > 50 -> NOT met
    assert alerts.alert_for(M(sku="1", current=80.0, drop_pct_from_high=0.0),
                            watchlist=wl) is None
    # drop threshold unmet also blocks (good_deal verdict but drop < 30)
    wl2 = [{"sku": "1", "threshold": {"min_drop_pct": 30}}]
    assert alerts.alert_for(M(sku="1", at_all_time_low=False, drop_pct_from_high=20.0,
                              current=80.0, high=100.0), watchlist=wl2) is None


# The GATE is the new behaviour; verdict is still the SSOT.
def test_gate_still_uses_price_verdict_sstot():
    # a 'stable' verdict is not an alarm verdict, so the gate never fires it even
    # if the sku is watched + threshold met -> the verdict rule still governs.
    wl = [{"sku": "1", "threshold": {}}]
    assert alerts.alert_for(M(sku="1", at_all_time_low=False, drop_pct_from_high=10.0,
                              current=90.0, high=100.0, low=80.0), watchlist=wl) is None


# AC5 via scan: an empty watchlist makes scan return nothing for a fired set.
def test_scan_empty_watchlist_silences_everything():
    m = M(sku="1", at_all_time_low=True)
    assert alerts.scan([m], state={}, watchlist=[]) == ([], {})


# The dedup state still works THROUGH the gate.
def test_scan_dedup_with_watchlist():
    m = M(sku="1", at_all_time_low=True)
    wl = [{"sku": "1", "threshold": {"target": 100}}]
    fresh, state = alerts.scan([m], state={}, watchlist=wl)
    assert [a["sku"] for a in fresh] == ["1"]
    again, _ = alerts.scan([m], state=state, watchlist=wl)
    assert again == []                       # notify once per event, through the gate


# watchlist=None disables the gate (legacy verdict-only — the existing suite).
def test_none_watchlist_is_legacy_no_gate():
    assert alerts.alert_for(M(sku="1", at_all_time_low=True), watchlist=None) is not None


# ---------------- DECOUPLING: toggling the watchlist never touches the series ----------------

def test_watchlist_toggle_does_not_mutate_history_data():
    """The time-series SSOT `history_data.json` must stay byte-identical when the
    watchlist is added to / removed from / saved. The two concerns are separate
    files, so personalizing the gate can never churn the observation series."""
    assert os.path.exists(watchlist.WATCHLIST_PATH)
    # the real time-series SSOT (loaded read-only, never written by the watchlist)
    hist_path = os.path.join(os.path.dirname(watchlist.WATCHLIST_PATH), "history_data.json")
    before = open(hist_path, encoding="utf-8").read()

    base = watchlist.load()                # the committed demo
    ghost = {"sku": "ZZZ-ghost", "name": "ghost", "threshold": {"target": 1}}
    on_path = os.path.join(history_dir(), "wl_on.json")
    off_path = os.path.join(history_dir(), "wl_off.json")

    # toggle ON: add a brand-new (untracked) sku + save
    watchlist.save(base + [ghost], on_path)
    assert ghost in watchlist.load(on_path)
    # toggle OFF: remove it again + save
    watchlist.save([e for e in watchlist.load(on_path) if e.get("sku") != "ZZZ-ghost"],
                   off_path)
    assert {e["sku"] for e in watchlist.load(off_path)} == {e["sku"] for e in base}

    after = open(hist_path, encoding="utf-8").read()
    assert before == after                 # history_data.json was NEVER touched
    # and the real committed watchlist SSOT is untouched too
    assert watchlist.load() == base


def history_dir():
    import tempfile
    d = tempfile.mkdtemp(prefix="wl-")
    return d
