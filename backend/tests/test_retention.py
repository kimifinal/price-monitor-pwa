"""Issue #5 — 保留策略 / drift 衛生: the rolling-window retention on the JSON SSOT.

These pin the issue's acceptance criteria, all OFFLINE + deterministic (no network,
no real time — a fixed `now` anchors every window):

  AC1  a configurable rolling window keeps only the most recent N days (so the
       append-only history_data.json stops growing without bound);
  AC2  synthetic-first eviction — a real observation outranks an equivalent-age
       synthetic, so old backfill/fallback points are dropped first and a sku with
       any real point keeps it; a pure-synthetic sku MAY be pruned;
  AC3  a sku whose whole series falls out of window is marked "discontinued" via a
       decoupled sidecar record (never a dangling row); a discontinued sku that is
       ALSO in watchlist.json is FLAGGED, not deleted (the #4 decoupling);
  AC4  apply_window + the refresh-path driver are idempotent + deterministic: a
       re-run on the already-pruned file is byte-identical;
  AC5  series integrity — after retention each remaining sku's series has no
       duplicates / broken / overlapping points, the window never cuts through a
       sku's needed points (it is always a contiguous tail), and nothing is
       fabricated (kept ⊆ original).

The window is anchored at the NEWEST observation (not the wall clock) so AC4 holds.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

import pytest

import history

# The fixed "now" every window is measured from — deterministic, offline.
NOW = datetime(2026, 11, 12)


def obs(sku, days_ago, price, synthetic=False, name=None, tag="3C",
        currency="TWD", source=None):
    """A history_data.json-shaped observation `days_ago` before NOW."""
    src = source if source is not None else ("backfill" if synthetic else "costco")
    return {
        "sku": str(sku),
        "name": name or f"name-{sku}",
        "tag": tag,
        "price": float(price),
        "currency": currency,
        "observed_at": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00"),
        "source": src,
        "synthetic": 1 if synthetic else 0,
    }


def ts_str(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT00:00:00")


def skus_of(records):
    return {str(r.get("sku")) for r in records}


def series_of(kept, sku):
    """A sku's kept points, ascending by observed_at."""
    rows = [r for r in kept if str(r.get("sku")) == sku]
    return rows


# ======================================================================
# AC1 — configurable rolling window
# ======================================================================

def test_window_keeps_recent_evicts_old(tmp_path):
    now = NOW
    pts = [obs("a", d, 100.0 + d, synthetic=True) for d in range(0, 200)]
    kept = history.apply_window(pts, window_days=90, now=now)
    tss = {r["observed_at"] for r in kept}
    assert ts_str(0) in tss                              # the newest survives
    assert ts_str(199) not in tss                        # a 199-day-old point is gone
    assert ts_str(100) not in tss                        # 100 days out (cutoff=90) gone
    # everything kept is strictly within the window
    for r in kept:
        assert (NOW - timedelta(days=90)) <= history._parse_ts(r["observed_at"]) <= NOW


def test_window_days_is_configurable(tmp_path):
    # a 14-day-old real point: kept by a big window, evicted by a tiny one
    pts = [
        obs("b", 0, 1.0, synthetic=True),
        obs("b", 100, 2.0, synthetic=False, source="costco"),   # a real, 100 days out
    ]
    big = skus_of(history.apply_window(pts, window_days=200, now=NOW))
    small = skus_of(history.apply_window(pts, window_days=30, now=NOW))
    assert "b" in big and "b" in small
    # under the 30-day window the 100-day-old REAL survives (AC2 keep-real) but the
    # pure-synthetic skus with no recent point would not — here the real keeps it.
    kept_small = history.apply_window(pts, window_days=30, now=NOW)
    kept_ts = {r["observed_at"] for r in kept_small}
    assert ts_str(100) in kept_ts            # real outranks the age cutoff
    assert ts_str(0) in kept_ts


def test_dump_observations_applies_window(tmp_path):
    art = str(tmp_path / "h.json")
    pts = [
        obs("c", 0, 1.0, synthetic=True),
        obs("c", 200, 2.0, synthetic=False, source="costco"),
    ]
    n = history.dump_observations(pts, art, window_days=30, now=NOW)
    loaded = history.load_observations(art)
    keep_ts = {r["observed_at"] for r in loaded}
    assert ts_str(200) in keep_ts            # real kept
    assert ts_str(0) in keep_ts


def test_dump_observations_default_never_prunes(tmp_path):
    # window_days=None (the legacy default) leaves a 200-day-old REAL in place
    art = str(tmp_path / "h.json")
    pts = [obs("d", 200, 9.0, synthetic=False, source="costco")]
    history.dump_observations(pts, art, now=NOW)
    loaded = history.load_observations(art)
    assert len(loaded) == 1 and loaded[0]["observed_at"] == ts_str(200)


def test_env_resolves_window_days(monkeypatch):
    assert history.resolve_window_days() == history.DEFAULT_WINDOW_DAYS  # 90 default
    monkeypatch.setenv("HISTORY_WINDOW_DAYS", "45")
    assert history.resolve_window_days() == 45
    monkeypatch.setenv("HISTORY_WINDOW_DAYS", "0")          # non-positive -> default
    assert history.resolve_window_days() == 90
    monkeypatch.setenv("HISTORY_WINDOW_DAYS", "notanumber")  # junk -> default
    assert history.resolve_window_days() == 90


# ======================================================================
# AC2 — synthetic-first eviction, real outranks equivalent-age synthetic
# ======================================================================

def test_synthetic_first_rescues_real_over_older_synthetic(tmp_path):
    # sku: an in-window synthetic (day 2), a real just OUTSIDE the window (day 9),
    # and a far-older synthetic (day 90). The real must be kept over the synthetic
    # that the window would otherwise drop; the far-older synthetic is evicted.
    pts = [
        obs("w", 2, 7.0, synthetic=True),
        obs("w", 9, 8.0, synthetic=False, source="costco"),
        obs("w", 90, 9.0, synthetic=True),
        obs("anchor", 0, 1.0, synthetic=True),   # keeps the window anchored at NOW
    ]
    kept = history.apply_window(pts, window_days=30, now=NOW)
    w = {r["observed_at"] for r in series_of(kept, "w")}
    assert ts_str(2) in w               # in-window synthetic kept
    assert ts_str(9) in w              # just-outside REAL kept (outranks the synthetic)
    assert ts_str(90) not in w         # the far-older synthetic is evicted first


def test_keep_real_points_when_fully_out_of_window(tmp_path):
    # A sku that has ANY real point keeps its real evidence even when the ENTIRE
    # series is out of the window; the synthetic side of it is dropped.
    pts = [
        obs("z", 50, 5.0, synthetic=True),
        obs("z", 40, 4.0, synthetic=False, source="costco"),
        obs("z", 30, 3.0, synthetic=False, source="costco"),
        obs("anchor", 0, 1.0, synthetic=True),
    ]
    kept = history.apply_window(pts, window_days=10, now=NOW)
    z = series_of(kept, "z")
    ts = {r["observed_at"] for r in z}
    assert ts_str(40) in ts and ts_str(30) in ts   # the two REAL points survive
    assert ts_str(50) not in ts                    # the older synthetic is gone


def test_pure_synthetic_out_of_window_is_pruned(tmp_path):
    # AC2: "if a sku has only-synthetic history, it may be pruned."
    pts = [
        obs("oldsyn", 400, 3.0, synthetic=True),
        obs("anchor", 0, 1.0, synthetic=True),
    ]
    kept = history.apply_window(pts, window_days=90, now=NOW)
    assert skus_of(kept) == {"anchor"}     # the pure-synthetic old sku is gone
    assert "oldsyn" in history.discontinued_skus(pts, window_days=90, now=NOW)


# ======================================================================
# AC3 — discontinued / orphan skus: sidecar record + watchlist FLAG (decoupled)
# ======================================================================

def test_discontinued_sidecar_records_latest_obs(tmp_path):
    pts = [
        obs("old1", 400, 3.0, synthetic=True, name="Old One"),
        obs("old1", 380, 3.5, synthetic=True, name="Old One"),
        obs("anchor", 0, 1.0, synthetic=True),
    ]
    recs = history.render_discontinued(pts, window_days=90, now=NOW)
    by_sku = {r["sku"]: r for r in recs}
    assert set(by_sku) == {"old1"}
    r = by_sku["old1"]
    assert r["discontinued"] is True
    assert r["last_observed_at"] == ts_str(380)    # its LATEST point, not the oldest
    assert r["price"] == 3.5
    assert r["watched"] is False                    # not in the (absent) watchlist


def test_discontinued_sku_has_no_dangling_row_in_series(tmp_path):
    pts = [
        obs("orphan", 500, 2.0, synthetic=True),
        obs("live", 0, 1.0, synthetic=False, source="costco"),
    ]
    kept = history.apply_window(pts, window_days=90, now=NOW)
    # the orphan sku has NO row left in the series (it is not dangling/broken),
    # but it IS discoverable via the sidecar.
    assert "orphan" not in skus_of(kept)
    assert "orphan" in {r["sku"] for r in history.render_discontinued(pts, window_days=90, now=NOW)}


def test_flag_discontinued_watchlist_does_not_mutate(tmp_path):
    pts = [
        obs("149699", 400, 3.0, synthetic=True, name="Discontinued Watched"),
        obs("3062725", 0, 1.0, synthetic=True, name="Still Watched"),
        obs("anchor", 0, 1.0, synthetic=True),
    ]
    wl = [
        {"sku": "149699", "name": "Discontinued Watched", "threshold": {"target": 1000}},
        {"sku": "3062725", "name": "Still Watched", "threshold": {"min_drop_pct": 15}},
        "junk",
        {"name": "no sku"},
    ]
    before = json.dumps(wl)
    disc = history.discontinued_skus(pts, window_days=90, now=NOW)
    flags = history.flag_discontinued_watchlist(wl, disc)
    # only the discontinued+watched sku is flagged
    flagged = {f["sku"] for f in flags}
    assert flagged == {"149699"}
    assert all(f["flag"] == "discontinued" for f in flags)
    assert flags[0]["threshold"] == {"target": 1000}
    # the watchlist list itself was NOT mutated (decoupling — #4)
    assert json.dumps(wl) == before


def test_flag_uses_record_list_too(tmp_path):
    # flag_discontinued_watchlist also accepts a list of sidecar records
    recs = [{"sku": "149699", "discontinued": True}]
    flags = history.flag_discontinued_watchlist([{"sku": "149699"}], recs)
    assert {f["sku"] for f in flags} == {"149699"}


def test_discontinued_watchlist_flags_surface_in_prune(tmp_path):
    art = str(tmp_path / "h.json")
    disc = str(tmp_path / "disc.json")
    pts = [
        obs("149699", 400, 3.0, synthetic=True, name="Old Watched"),
        obs("anchor", 0, 1.0, synthetic=False, source="costco"),
    ]
    history.dump_observations(pts, art)
    wl = [{"sku": "149699", "name": "Old Watched", "threshold": {"target": 100}}]
    out = history.prune_to_window(persist_path=art, discontinued_path=disc,
                                 window_days=90, watchlist=wl)
    flagged = {f["sku"] for f in out["watchlist_flags"]}
    assert "149699" in flagged             # flagged, not deleted from wl
    # the watchlist file itself was never created/touched
    assert not os.path.exists(str(tmp_path / "watchlist.json"))


# ======================================================================
# AC4 — idempotent + deterministic (re-run is byte-identical)
# ======================================================================

def test_apply_window_is_idempotent(tmp_path):
    pts = [
        obs("a", d, 1.0 + d, synthetic=True) for d in range(0, 120)
    ] + [
        obs("b", d, 5.0 + d, synthetic=False, source="costco") for d in range(0, 300)
    ] + [
        obs("oldsyn", 400, 9.0, synthetic=True),
        obs("mix", 9, 4.0, synthetic=False, source="costco"),
        obs("mix", 90, 99.0, synthetic=True),
    ]
    once = history.apply_window(pts, window_days=60, now=NOW)
    twice = history.apply_window(once, window_days=60, now=NOW)
    assert once == twice                       # pure-function idempotence


def test_dump_windowed_byte_identical_on_rerun(tmp_path):
    # AC4 "Prove it": writing a windowed file, then reading it back and re-applying
    # the window, produces a byte-identical file on the second run.
    art = str(tmp_path / "h.json")
    pts = [
        obs("a", d, 1.0 + d, synthetic=True) for d in range(0, 200)
    ] + [
        obs("b", d, 5.0 + d, synthetic=False, source="costco") for d in range(0, 200)
    ] + [
        obs("oldsyn", 400, 9.0, synthetic=True, name="old synthetic"),
        obs("live", 0, 7.0, synthetic=False, source="costco"),
    ]
    history.dump_observations(pts, art, window_days=90, now=NOW)
    b1 = open(art, encoding="utf-8").read()
    # 2nd refresh: load the pruned SSOT, re-apply the window, rewrite
    reloaded = history.load_observations(art)
    history.dump_observations(reloaded, art, window_days=90, now=NOW)
    b2 = open(art, encoding="utf-8").read()
    assert b1 == b2                            # byte-identical, no churn


def test_prune_to_window_sidecar_byte_identical_on_rerun(tmp_path):
    # the discontinued sidecar must also be idempotent across re-runs.
    art = str(tmp_path / "h.json")
    disc = str(tmp_path / "disc.json")
    pts = [
        obs("oldsyn", 400, 9.0, synthetic=True, name="old synthetic"),
        obs("live", 0, 7.0, synthetic=False, source="costco"),
        obs("recent", 5, 2.0, synthetic=True),
    ]
    history.dump_observations(pts, art)
    history.prune_to_window(persist_path=art, discontinued_path=disc, window_days=90)
    s1 = open(disc, encoding="utf-8").read()
    # a SECOND run on the already-windowed file re-derives the same sidecar
    history.prune_to_window(persist_path=art, discontinued_path=disc, window_days=90)
    s2 = open(disc, encoding="utf-8").read()
    assert s1 == s2                            # sidecar idempotent
    # and the discontinued sku is still recorded (its record accumulated, not wiped)
    assert {r["sku"] for r in history.load_discontinued(disc)} == {"oldsyn"}


def test_windowed_rerun_no_diff_on_real_artifact():
    # The ACTUAL committed SSOT under the default 90-day window is a no-op: every
    # current observation is within 90 days, so re-windowing is byte-identical.
    obs = history.load_observations()
    assert obs
    once = history.apply_window(obs, window_days=90)
    twice = history.apply_window(once, window_days=90)
    assert once == twice
    assert len(once) == len(obs)              # nothing evicted: it IS a no-op


# ======================================================================
# AC5 — series integrity after retention
# ======================================================================

def _series_intact(kept, originals):
    """The AC5 invariants on a windowed result vs its originals."""
    bysku = defaultdict(list)
    for r in kept:
        bysku[str(r["sku"])].append(r)
    # no fabricated points: every kept obs exists verbatim in the originals
    orig_keys = {(str(o["sku"]), o["observed_at"], o["source"]) for o in originals}
    for sku, rows in bysku.items():
        keys = [(str(o["sku"]), o["observed_at"], o["source"]) for o in rows]
        # no duplicate points
        assert len(keys) == len(set(keys)), f"dup points for {sku}"
        # timestamps non-decreasing (no broken/overlapping ordering)
        ts_seq = [history._parse_ts(o["observed_at"]) for o in sorted(rows, key=history._obs_ts_key)]
        assert all(a <= b for a, b in zip(ts_seq, ts_seq[1:]))
        # subset of the originals (no mis-deletion into fabricated data)
        assert set(keys) <= set(orig_keys), f"fabricated points for {sku}"
        # contiguous tail: the kept series is the tail of the original series, with
        # nothing of its needed points cut out of the middle.
        orig_sorted = sorted([o for o in originals if str(o["sku"]) == sku],
                             key=history._obs_ts_key)
        orig_ts = [o["observed_at"] for o in orig_sorted]
        kept_ts = [r["observed_at"] for r in sorted(rows, key=history._obs_ts_key)]
        assert kept_ts == orig_ts[len(orig_ts) - len(kept_ts):], \
            f"window cut through {sku}'s needed points"
        assert all(o["observed_at"] in orig_ts for o in rows)


def test_series_intact_no_dup_no_gap_no_break(tmp_path):
    # A realistic per-sku layout: a block of SYNTHEtics at the old end, then a
    # contiguous block of REAL points at the new end — plus discontinued + real
    # -evidence skus. After the window each kept series is intact.
    originals = []
    # clean "tail" sku: synthetics older than the reals, window cuts only the synth
    originals += [obs("clean", d, 100.0 + d, synthetic=True, source="backfill")
                  for d in range(60, 46, -1)]        # days 60..47 (old synthetics)
    originals += [obs("clean", d, 110.0 - d, synthetic=False, source="costco")
                  for d in (30, 20, 10, 0)]          # days 30..0 (reals, in-window)
    kept = history.apply_window(originals, window_days=30, now=NOW)
    _series_intact(kept, originals)
    # the window cut through only the SYNTHETIC tail, not the real evidence
    clean_ts = {r["observed_at"] for r in series_of(kept, "clean")}
    assert ts_str(0) in clean_ts and ts_str(30) in clean_ts
    assert ts_str(47) not in clean_ts and ts_str(60) not in clean_ts


def test_no_fabrication_kept_subset_of_original(tmp_path):
    pts = [obs("a", d, 1.0 + d, synthetic=True) for d in range(0, 100)]
    kept = history.apply_window(pts, window_days=30, now=NOW)
    assert len(kept) < len(pts)
    assert all(o in pts for o in kept)          # nothing invented


# ======================================================================
# decoupling — #4: retention NEVER rewrites watchlist.json
# ======================================================================

def test_prune_to_window_never_writes_watchlist(tmp_path, monkeypatch):
    # Point the watchlist SSOT somewhere writable and prove the retention path does
    # not open it for writing.
    art = str(tmp_path / "h.json")
    disc = str(tmp_path / "disc.json")
    wl_path = str(tmp_path / "watchlist.json")
    history.dump_observations(
        [obs("oldsyn", 400, 9.0, synthetic=True, name="old"),
         obs("live", 0, 1.0, synthetic=False, source="costco")],
        art,
    )
    monkeypatch.setattr("watchlist.WATCHLIST_PATH", wl_path)
    out = history.prune_to_window(persist_path=art, discontinued_path=disc,
                                 window_days=90, watchlist=None)
    assert out["discontinued"] == ["oldsyn"]
    # watchlist.json must NOT have been touched by the retention path
    assert not os.path.exists(wl_path)


def test_window_does_not_touch_watchlist_file_directly(tmp_path):
    # The most direct decoupling check: apply_window / render_discontinued operate
    # only on the observation list; a watchlist file on disk is left byte-identical.
    art = str(tmp_path / "h.json")
    wl = str(tmp_path / "watchlist.json")
    payload = [{"sku": "oldsyn", "name": "old", "threshold": {"target": 1}}]
    with open(wl, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    before = open(wl, encoding="utf-8").read()
    history.dump_observations(
        [obs("oldsyn", 400, 9.0, synthetic=True), obs("live", 0, 1.0, synthetic=False)],
        art, window_days=30, now=NOW,
    )
    history.render_discontinued(history.load_observations(art), window_days=30, now=NOW)
    after = open(wl, encoding="utf-8").read()
    assert before == after                      # watchlist.json never written


# ======================================================================
# hardening — timestamp parsing / flag variants / bad-input tolerance
# ======================================================================

def test_parse_ts_variants():
    # datetime input passes through naive; 'Z', date-only, and 'T'-forms parse
    assert history._parse_ts(NOW) == NOW.replace(tzinfo=None)
    assert history._parse_ts("2026-11-12T00:00:00") == datetime(2026, 11, 12)
    assert history._parse_ts("2026-11-12") == datetime(2026, 11, 12)
    # a trailing 'Z' is stripped and parsed as naive
    assert history._parse_ts("2026-11-12T00:00:00Z") == datetime(2026, 11, 12)
    # a value the parser can't understand raises ValueError (surfaced, not swallowed
    # except where newest_ts/_parse_ts is wrapped to skip it)
    with pytest.raises(ValueError):
        history._parse_ts("not-a-time")


def test_syn_int_variants():
    assert history._syn_int({"synthetic": 1}) == 1
    assert history._syn_int({"synthetic": 0}) == 0
    assert history._syn_int({"synthetic": True}) == 1
    assert history._syn_int({"synthetic": "1"}) == 1
    assert history._syn_int({"synthetic": "true"}) == 1
    assert history._syn_int({}) == 0                 # absent -> treated as real (0)
    assert history._syn_int({"synthetic": None}) == 0
    assert history._syn_int({"synthetic": "garbage"}) == 0   # junk -> real(0)
    # a real observation must outrank a synthetic, regardless of spelling
    assert history._is_real({"synthetic": 0}) is True
    assert history._is_real({"synthetic": "1"}) is False


def test_newest_ts_skips_junk(tmp_path):
    # newest_ts tolerates non-dict / unparseable / missing entries (offline-safe)
    assert history.newest_ts([]) is None
    junk = [
        {"no_observed_at": 1},                              # missing -> skipped
        "i am not a dict",                                  # non-dict -> skipped
        {"observed_at": "garbage"},                         # unparseable -> skipped
        obs("good", 3, 5.0),                                # the real anchor
    ]
    assert history.newest_ts(junk) == history._parse_ts(ts_str(3))


def test_apply_window_empty_and_anchor_none(tmp_path):
    assert history.apply_window([]) == []                         # empty -> empty
    # a list whose every timestamp is unparseable has no anchor -> cutoff None -> []
    no_anchor = [{"sku": "x", "observed_at": "garbage", "price": 1.0}]
    assert history.apply_window(no_anchor, window_days=30) == []


def test_as_dt_variants():
    assert history._as_dt(None) is None
    assert history._as_dt(NOW) == NOW.replace(tzinfo=None)
    assert history._as_dt("2026-01-01T00:00:00") == datetime(2026, 1, 1)


def test_flag_discontinued_watchlist_variants(tmp_path):
    # accepts either a set of skus or a list of (possibly mixed) records
    recs_mixed = ["149699", {"sku": "3062725", "discontinued": True}, "junk", 7]
    wl = [
        {"sku": "149699", "name": "A"},
        {"sku": "3062725", "name": "B"},
        {"sku": 999, "name": "not discontinued"},
        "not a dict",
        {"name": "no sku"},
    ]
    flags = history.flag_discontinued_watchlist(wl, recs_mixed)
    flagged = {f["sku"] for f in flags}
    assert flagged == {"149699", "3062725"}
    assert all(f["flag"] == "discontinued" for f in flags)
    # no discontinued skus -> no flags; the watchlist is never mutated
    assert history.flag_discontinued_watchlist(wl, set()) == []
    assert history.flag_discontinued_watchlist([], None) == []


def test_prune_to_window_accumulates_then_reactivates(tmp_path):
    # A sku can re-enter the window and drop out of the "discontinued" sidecar.
    art = str(tmp_path / "h.json")
    disc = str(tmp_path / "disc.json")
    # oldsyn is 400d old AND synthetic, but a fresh "live" sku anchors the window
    # at NOW so oldsyn is genuinely out of it.
    old = [obs("oldsyn", 400, 9.0, synthetic=True, name="old"),
           obs("live", 0, 1.0, synthetic=False, source="costco")]
    history.dump_observations(old, art)
    out1 = history.prune_to_window(persist_path=art, discontinued_path=disc, window_days=90)
    assert "oldsyn" in out1["discontinued"]
    assert {r["sku"] for r in history.load_discontinued(disc)} == {"oldsyn"}
    # now oldsyn gets a fresh IN-WINDOW real point: it reactivates and leaves the
    # sidecar (the sidecar must not keep a sku that came back).
    reloaded = history.load_observations(art)
    reloaded.append(obs("oldsyn", 1, 5.0, synthetic=False, source="costco"))
    history.dump_observations(reloaded, art)
    out2 = history.prune_to_window(persist_path=art, discontinued_path=disc, window_days=90)
    assert "oldsyn" not in out2["discontinued"]
    assert {r["sku"] for r in history.load_discontinued(disc)} == set()
