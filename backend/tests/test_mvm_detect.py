"""B1 (Tier B of #35) — offline tests for MVM new-tab detection.

AC coverage (mvm_detect):
  * SILENT  — feeding only the manifest's own 6 tab urls yields [] (no false
    new-tab alarm).
  * NEW     — feeding a 7th url (a tab absent from the manifest) is detected.
  * DUP     — a repeat url is reported once (de-duplicated).
Plus the hard invariants: a diff against an EMPTY manifest stays silent (a base-less
diff is undefined), 0-count manifest tabs are still "known" (not falsely new), and
the whole thing is stdlib-only / offline.
"""
import json
from pathlib import Path

import mvm_detect

MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "data"
                       / "costco_mvm" / "manifest.json").read_text(encoding="utf-8"))


def _known_urls():
    """The 6 known tab urls, exactly as mvm_detect derives them."""
    return [mvm_detect.tab_url(MANIFEST, t["tab_id"]) for t in MANIFEST["tabs"]]


def _new_url():
    return "https://www.costco.com.tw/content/fy27p5-mvm2-w1"


# --------------------------- invariants of the manifest ---------------------------

def test_manifest_is_the_six_tab_baseline():
    assert len(MANIFEST["tabs"]) == 6                     # 6-tab SSOT
    ids = [t["tab_id"] for t in MANIFEST["tabs"]]
    assert ids == ["fy27p3-mvm2-weekday", "fy27p3-mvm2-w1",
                   "fy27p4-mvm2-cyber", "fy27p4-mvm2-cyberland",
                   "fy27p4-mvm2-weekday", "fy27p4-mvm2-w2"]
    assert mvm_detect.known_tab_ids(MANIFEST) == set(map(str, ids))
    # tab_id -> url mapping (only the first tab carries an explicit url; the rest
    # are derived as content/{tab_id})
    u = mvm_detect.tab_url(MANIFEST, "fy27p3-mvm2-w1")
    assert u == "https://www.costco.com.tw/content/fy27p3-mvm2-w1"
    assert u.endswith("/fy27p3-mvm2-w1")
    # the derived url maps BACK to the same tab_id
    assert mvm_detect.tab_id_from_url(u) == "fy27p3-mvm2-w1"


# --------------------------- AC: silent on the known six ---------------------------

def test_silent_when_only_known_urls_are_observed():
    # the golden AC: feed the original 6 urls -> no new tab, no false alarm
    out = mvm_detect.detect_new_tabs(_known_urls(), MANIFEST)
    assert out == []
    assert mvm_detect.detect_new_tabs(list(_known_urls()), MANIFEST) == []   # order-invariant
    assert mvm_detect.detect_new_tabs([], MANIFEST) == []
    assert mvm_detect.detect_new_tabs(None, MANIFEST) == []


def test_zero_count_manifest_tab_is_known_not_new():
    # fy27p4-mvm2-cyberland has count 0 in the manifest but IS a known tab;
    # observing its url must NOT be a false "new tab" alarm.
    url = mvm_detect.tab_url(MANIFEST, "fy27p4-mvm2-cyberland")
    assert mvm_detect.detect_new_tabs([url], MANIFEST) == []


# --------------------------- AC: a new 7th tab is detected ---------------------------

def test_detects_a_new_seventh_tab():
    observed = _known_urls() + [_new_url()]
    out = mvm_detect.detect_new_tabs(observed, MANIFEST)
    assert out == ["fy27p5-mvm2-w1"]               # exactly the one new tab id
    # the new tab is reconstructable (url + label) for B3's alert
    info = mvm_detect.describe_new_tab("fy27p5-mvm2-w1", observed, MANIFEST)
    assert info["tab_id"] == "fy27p5-mvm2-w1"
    assert info["url"].endswith("/fy27p5-mvm2-w1")
    assert "新 MVM 檔期" in info["label"]


def test_new_tab_uses_the_observed_exact_url_when_seen():
    # a new tab we actually observed is reported with its observed url, not a guess
    obs_url = "https://www.costco.com.tw/content/fy27p5-mvm2-w1?ref=listing"
    info = mvm_detect.describe_new_tab("fy27p5-mvm2-w1", [obs_url], MANIFEST)
    assert info["url"] == obs_url                       # exact url wins
    # a new tab we did NOT observe -> reconstructed from content base
    info2 = mvm_detect.describe_new_tab("fy27p5-mvm2-w1", [], MANIFEST)
    assert info2["url"] == "https://www.costco.com.tw/content/fy27p5-mvm2-w1"


# --------------------------- de-dup + order + robustness ---------------------------

def test_duplicate_new_url_reported_once():
    observed = [MANIFEST["tabs"][0]["url"], _new_url(), _new_url()]
    out = mvm_detect.detect_new_tabs(observed, MANIFEST)
    assert out == ["fy27p5-mvm2-w1"]                   # deduped to a single hit


def test_new_tabs_preserve_first_seen_order_and_dedup():
    observed = (_known_urls()
                + ["https://www.costco.com.tw/content/fy27p5-mvm2-w1"]
                + ["https://www.costco.com.tw/content/fy27p5-mvm2-cyber?x=1"]  # dup id via query
                + ["https://www.costco.com.tw/content/fy27p6-mvm2-w1"])
    out = mvm_detect.detect_new_tabs(observed, MANIFEST)
    assert out == ["fy27p5-mvm2-w1", "fy27p5-mvm2-cyber", "fy27p6-mvm2-w1"]
    # each new id appears exactly once
    assert len(out) == len(set(out))


def test_query_string_and_trailing_slash_are_ignored():
    # a known url with junk query params / trailing slash is STILL known -> silent
    noisy = [mvm_detect.tab_url(MANIFEST, t["tab_id"]) + "?ref=x#/frag"
             for t in MANIFEST["tabs"]]
    assert mvm_detect.detect_new_tabs(noisy, MANIFEST) == []


def test_bare_tab_id_also_detected():
    # mvm_detect accepts both full urls and bare tab ids as "observed"
    out = mvm_detect.detect_new_tabs(["fy27p5-mvm2-w1"], MANIFEST)
    assert out == ["fy27p5-mvm2-w1"]


def test_empty_manifest_stays_silent():
    # no baseline => a diff is undefined => NEVER claim "everything is new"
    assert mvm_detect.detect_new_tabs([_new_url(), "https://x/y/fy99"], {}) == []
    assert mvm_detect.detect_new_tabs([_new_url()], None) == []
    assert mvm_detect.detect_new_tabs(["whatever"], {"tabs": []}) == []


def test_garbage_observed_is_skipped_not_a_false_new():
    urlid = "https://www.costco.com.tw/content/fy27p5-mvm2-w1"
    out = mvm_detect.detect_new_tabs([urlid, "", "   ", None, 12345, "///"], MANIFEST)
    assert out == ["fy27p5-mvm2-w1"]            # junk dropped, the real new tab kept


def test_content_base_resolves_from_manifest_top_level_url():
    # when no tab carries an explicit url, fall back to the manifest's top url
    bare = {"url": "https://www.costco.com.tw/content/fy27z-mvm2-x", "tabs": [
        {"tab_id": "fy27z-mvm2-x"}, {"tab_id": "fy27z-mvm2-y"}]}
    assert mvm_detect.content_base(bare) == "https://www.costco.com.tw/content/"
    assert mvm_detect.tab_id_from_url(
        "https://www.costco.com.tw/content/fy27z-mvm2-y?a=b") == "fy27z-mvm2-y"


def test_load_manifest_reads_the_tracked_ssot():
    m = mvm_detect.load_manifest()
    assert m.get("tabs") and len(m["tabs"]) == 6
    # a missing / corrupt manifest degrades to {} WITHOUT raising
    assert mvm_detect.load_manifest(str(Path("/no/such/manifest.json"))) == {}
