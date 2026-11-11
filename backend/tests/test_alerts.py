"""Tests for the verdict-based alert scanner (#2).

Every assertion is offline + deterministic — no network, no creds. They pin the
three golden-rule ACs: (a) the trigger REUSES models.price_verdict (the SSOT),
(b) we NEVER fire on synthetic/fallback data, (c) dedup => 'notify once per event'.
"""
import alerts
import models


def M(**over):
    base = dict(sku="1", name="Widget", tag="3C", points=14,
                current=80.0, low=80.0, high=100.0,
                drop_pct_from_high=20.0, at_all_time_low=True,
                current_is_real=True, last_seen="2026-11-11T00:00:00")
    base.update(over)
    return base


# --------------------- trigger reuses the price_verdict SSOT ---------------------

def test_all_time_low_triggers_alert():
    a = alerts.alert_for(M())
    assert a is not None
    assert a["verdict"] == "all_time_low"
    assert a["label"] == "歷史最低 👍"           # the label came from the SSOT
    assert a["price"] == 80.0
    assert a["as_of"] == "2026-11-11"


def test_good_deal_triggers_alert():
    # >= GOOD_DEAL_DROP (15) and not near high -> 'good_deal' -> alarm
    a = alerts.alert_for(M(at_all_time_low=False, drop_pct_from_high=16.0, current=84.0, low=80.0))
    assert a is not None and a["verdict"] == "good_deal"


def test_stable_does_not_alert():
    assert alerts.alert_for(M(at_all_time_low=False, drop_pct_from_high=10.0, high=100.0,
                              current=90.0, low=80.0)) is None


def test_near_high_does_not_alert():
    assert alerts.alert_for(M(at_all_time_low=False, drop_pct_from_high=3.0,
                              current=97.0, low=80.0)) is None


# --------------------- the hard AC: never fire on synthetic/fallback ---------------------

def test_no_alert_on_synthetic_data_only():
    # an at-all-time-low SKU with ONLY a backfill (no real point yet) must stay quiet
    assert alerts.alert_for(M(current_is_real=False)) is None


def test_empty_series_does_not_alert():
    assert alerts.alert_for({"sku": "x", "points": 0}) is None
    assert alerts.alert_for({}) is None


# --------------------- dedup: notify once per event ---------------------

def test_scan_dedups_same_event_once():
    m = M(sku="1")
    fresh, state = alerts.scan([m], state={})
    assert len(fresh) == 1
    # same scan, same state => nothing new
    again, _ = alerts.scan([m], state=state)
    assert again == []


def test_new_event_refires_but_old_does_not():
    low = M(sku="1", at_all_time_low=True, drop_pct_from_high=20.0, current=80.0)
    good = M(sku="2", at_all_time_low=False, drop_pct_from_high=16.0, current=84.0, low=80.0)
    fresh, state = alerts.scan([low], state={})
    assert [a["sku"] for a in fresh] == ["1"]
    # add a genuinely new verdict on another sku -> only the new one fires
    fresh2, _ = alerts.scan([low, good], state=state)
    assert [a["sku"] for a in fresh2] == ["2"]   # sku 1 deduped, sku 2 new


def test_scan_only_fires_on_real_among_mixed():
    real_low = M(sku="1", current_is_real=True)
    synth_low = M(sku="2", current_is_real=False)   # at low but no real point yet
    fresh, _ = alerts.scan([synth_low, real_low], state={})
    assert [a["sku"] for a in fresh] == ["1"]      # synthetic one is filtered out


# --------------------- custom policy is honoured ---------------------

def test_policy_narrows_which_verdicts_alert():
    a = alerts.alert_for(M(at_all_time_low=True, drop_pct_from_high=16.0, current=84.0),
                         policy={"alarm_verdicts": ("all_time_low",)})
    assert a is not None and a["verdict"] == "all_time_low"
    # narrow policy that excludes good_deal: a pure good_deal must NOT fire
    assert alerts.alert_for(M(at_all_time_low=False, drop_pct_from_high=16.0),
                            policy={"alarm_verdicts": ("all_time_low",)}) is None


# --------------------- dedup state is a durable, deterministic JSON SSOT ---------------------

def test_state_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    alerts.save_state({"1": ["1|all_time_low|2026-11-11"]}, p)
    reloaded = alerts.load_state(p)
    assert reloaded == {"1": ["1|all_time_low|2026-11-11"]}
    # missing file => empty state
    assert alerts.load_state(str(tmp_path / "nope.json")) == {}


# --------------------- price_verdict is literally reused, not re-implemented ---------------------

def test_uses_the_shared_sst_rule():
    # prove both sides share ONE rule: a metrics dict that price_verdict calls a
    # 'good_deal' must also produce a 'good_deal' alert.
    m = M(at_all_time_low=False, drop_pct_from_high=18.0, current=80.0, low=70.0, high=100.0)
    assert models.price_verdict(m)["verdict"] == "good_deal"
    assert alerts.alert_for(m)["verdict"] == "good_deal"
