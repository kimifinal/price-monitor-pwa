"""SSOT tests for the historical-price verdict (backend half).

`price_verdict` must stay in lockstep with `frontend/src/lib/monitor.js`'
`priceVerdict`. These pin the thresholds + the branch logic so the two sides
can't drift.
"""
from models import price_verdict, AT_LOW_TOL, GOOD_DEAL_DROP, NEAR_HIGH_DROP


def test_unknown_when_no_history():
    assert price_verdict({"points": 0}) == {
        "verdict": "unknown", "label": "無歷史資料", "drop_pct": 0.0
    }
    assert price_verdict({})["verdict"] == "unknown"
    assert price_verdict(None)["verdict"] == "unknown"


def test_all_time_low_takes_priority():
    # at_all_time_low wins regardless of the drop magnitude
    m = {"points": 10, "at_all_time_low": True, "drop_pct_from_high": 40.0}
    v = price_verdict(m)
    assert v["verdict"] == "all_time_low"
    assert v["drop_pct"] == 40.0
    assert "最低" in v["label"]


def test_good_deal_above_threshold():
    m = {"points": 5, "at_all_time_low": False, "drop_pct_from_high": 20.0}
    assert price_verdict(m)["verdict"] == "good_deal"


def test_stable_between_thresholds():
    # 8% drop: below GOOD_DEAL_DROP (not a great deal) and above NEAR_HIGH_DROP
    m = {"points": 5, "at_all_time_low": False, "drop_pct_from_high": 8.0}
    assert price_verdict(m)["verdict"] == "stable"


def test_near_high_below_threshold():
    m = {"points": 5, "at_all_time_low": False, "drop_pct_from_high": 2.0}
    assert price_verdict(m)["verdict"] == "near_high"


def test_thresholds_are_exported_constants():
    # the JS mirror references these same numbers; pin them so a drift is loud.
    assert GOOD_DEAL_DROP == 15.0
    assert NEAR_HIGH_DROP == 5.0
    assert AT_LOW_TOL == 1.001
