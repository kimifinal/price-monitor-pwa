"""Tier A (#35) — offline tests for the Costco item-layer detectChange engine.

All assertions are offline + deterministic (no network, no real Costco API):
  * A1  price_drop / out_of_stock / new_item — each of the three change kinds
        has a fixture that FIRES, plus the *silence* guarantee (an unchanged
        sku produces NO event — no false alert).
  * A2  decal-driven diff on a SAMPLE of real `data/costco_catalog/products.
        full.json` items: a 限時特價 / 優惠特價 / 網路獨家 / 新品推薦 transition
        fires the right event; an identical sample is silent.
  * 二次 parse — raw API fields are JSON strings (`"{"intValue":999}"`,
        `"{"stockLevelStatus":"inStock"}"`, `decalData:[{value:{altText}}]`);
        the normalizer must parse them.
  * A3  refresh_catalog fallback: HTTP 404 / 429 / connection error -> fall back
        to the last saved snapshot, do NOT overwrite history, do NOT fire a
        false alert, and LOG "回退到快照"  (mirrors test_basket's snapshot mode).

Alert dedup + delivery reuse `alerts` (alert_signature / scan / emit).
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

import alerts
import detect_change as dc

BACKEND = Path(__file__).resolve().parents[1]
CATALOG = Path(__file__).resolve().parents[2] / "data" / "costco_catalog" / "products.full.json"
HISTORY = BACKEND / "history_data.json"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _item(sku, price, base=0.0, stock="inStock", decals=None, name=None):
    """A normalized-fixture item (products.full.json shape)."""
    return {
        "sku": str(sku),
        "name": name or f"SKU {sku}",
        "price": price,
        "basePrice": base if base else price,   # no discount by default
        "stock": stock,
        "decals": list(decals or []),
        "url": f"/p/{sku}",
    }


def _load_catalog():
    with open(CATALOG, encoding="utf-8") as f:
        return json.load(f)


def _events_of_kind(events, kind):
    return [e for e in events if e["type"] == kind]


# --------------------------------------------------------------------------
# A1 — the three change kinds each FIRE
# --------------------------------------------------------------------------

def test_price_drop_when_price_falls_vs_previous():
    prev = [_item("100", 1000.0, base=1200.0)]          # 1000 < 1200 already on sale
    cur = [_item("100", 900.0, base=1200.0)]            # 900 < 1000 -> a genuine fall
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    drops = _events_of_kind(events, "price_drop")
    assert len(drops) == 1
    assert drops[0]["sku"] == "100"
    assert "較上次下跌" in drops[0]["reason"]
    assert drops[0]["drop_pct"] == 10.0
    assert drops[0]["real"] is True
    assert drops[0]["as_of"] == "2026-11-18"


def test_price_drop_when_sku_goes_on_sale_price_lt_baseprice():
    prev = [_item("200", 1000.0, base=1000.0)]          # full price
    cur = [_item("200", 850.0, base=1000.0)]            # now 850 < 1000 -> a new sale
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    drops = _events_of_kind(events, "price_drop")
    assert len(drops) == 1
    assert "basePrice" in drops[0]["reason"]             # the price<basePrice branch


def test_out_of_stock_transition_fires():
    prev = [_item("300", 500.0, stock="inStock")]
    cur = [_item("300", 500.0, stock="outOfStock")]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    oos = _events_of_kind(events, "out_of_stock")
    assert len(oos) == 1
    assert oos[0]["sku"] == "300"
    assert "缺貨" in oos[0]["reason"]


def test_new_item_when_sku_absent_from_previous():
    prev = [_item("100", 100.0), _item("200", 200.0)]
    cur = prev + [_item("400", 400.0, name="Brand New Gadget")]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    new = _events_of_kind(events, "new_item")
    assert [e["sku"] for e in new] == ["400"]
    assert new[0]["name"] == "Brand New Gadget"
    assert "新增 SKU" in new[0]["reason"]


# --------------------------------------------------------------------------
# A1 — silence: an unchanged snapshot produces NO events (no false alert)
# --------------------------------------------------------------------------

def test_no_events_when_snapshot_unchanged():
    items = [_item("100", 1000.0, base=1000.0, decals=["速配"])]
    events = dc.detect_change(list(items), list(items), as_of="2026-11-18")
    assert events == []


def test_still_on_sale_in_both_snapshots_is_silent():
    # on sale in prev AND in cur with no change must NOT re-fire every day
    items = [_item("100", 800.0, base=1000.0, decals=["Costco好市多限時特價商品"])]
    assert dc.detect_change(list(items), list(items), as_of="2026-11-18") == []


def test_no_new_decal_keeps_silence():
    # speed-ship decal (速配) is NOT a deal/new signal -> no fire
    items = [_item("100", 800.0, base=800.0, decals=["速配"])]
    cur = [_item("100", 800.0, base=800.0, decals=["速配"])]
    assert dc.detect_change(items, cur, as_of="2026-11-18") == []


# --------------------------------------------------------------------------
# A2 — decal-driven signals (transitions), incl. on REAL catalog data
# --------------------------------------------------------------------------

def test_deal_decal_transition_fires_price_drop():
    # a newly-appeared 限時特價 decal counts as a price drop even when price
    # itself is unchanged
    prev = [_item("111", 999.0, base=999.0, decals=[])]
    cur = [_item("111", 999.0, base=999.0, decals=["Costco好市多限時特價商品"])]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    drops = _events_of_kind(events, "price_drop")
    assert len(drops) == 1
    assert drops[0]["decal"] is True                       # decal-driven
    assert "限時特價" in drops[0]["reason"]


def test_new_decal_transition_fires_new_item_on_existing_sku():
    prev = [_item("222", 499.0, base=499.0, decals=["速配"])]
    cur = [_item("222", 499.0, base=499.0,
                  decals=["速配", "Costco好市多網路獨家商品"])]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    new = _events_of_kind(events, "new_item")
    assert len(new) == 1
    assert new[0]["decal"] is True
    assert "網路獨家" in new[0]["reason"]


def _sample():
    """Pick a small, deterministic sample from the REAL full catalog: items that
    carry the decal signals + a couple of out-of-stock + empty-decal in-stock
    items. Each list is non-empty so the tests have real material to assert on."""
    prods = _load_catalog().get("products", [])
    deals, news, stocked, oos = [], [], [], []
    for p in prods:
        dec = " ".join(p.get("decals") or [])
        pr, bp, st = p.get("price"), p.get("basePrice"), str(p.get("stock", "")).lower()
        if st == "outofstock" and len(oos) < 1:
            oos.append(p)
        elif pr is not None and isinstance(bp, (int, float)) and pr < bp \
                and "限時特價" in dec and len(deals) < 2:
            deals.append(p)
        elif "新品推薦" in dec and len(news) < 2:
            news.append(p)
        elif not (p.get("decals") or []) and st == "instock" and len(stocked) < 2:
            stocked.append(p)
        if len(deals) >= 2 and len(news) >= 2 and len(stocked) >= 2 and len(oos) >= 1:
            break
    return deals, news, stocked, oos


def test_decal_diff_fires_on_real_catalog_sample():
    """A daily-diff over a REAL `products.full.json` sample: a price/stock/
    decal transition in `cur` fires the right event, and the untouched item
    stays silent — proving the decal pipeline on the actual data shape."""
    deals, news, stocked, oos = _sample()
    assert deals and oos and stocked and news, "fixture: need real catalog samples"
    deal = deals[0]
    oos_item = oos[0]
    untouched = next(s for s in stocked
                     if s["sku"] not in (deal["sku"], oos_item["sku"]))

    # yesterday -> today, perturbing exactly one field per signal
    prev = [dict(deal, price=deal["price"]),
            dict(oos_item, stock="inStock"),
            dict(untouched)]
    cur = [
        dict(deal, price=deal["price"] - 100),                 # price fall -> price_drop
        dict(oos_item, stock="outOfStock"),                    # inStock -> outOfStock
        dict(untouched),                                       # unchanged -> SILENT
        _item("987654", 1234.0, base=1234.0,
              decals=["Costco好市多新品推薦"]),                # new sku + new decal
    ]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    by = {}
    for e in events:
        by.setdefault(e["type"], []).append(e)

    assert untouched["sku"] not in {e["sku"] for e in events}        # unchanged => silence
    assert any(e["sku"] == deal["sku"] for e in by.get("price_drop", []))
    assert any("較上次下跌" in e["reason"] for e in by.get("price_drop", []))
    assert oos_item["sku"] in {e["sku"] for e in by.get("out_of_stock", [])}
    new = by.get("new_item", [])
    assert "987654" in {e["sku"] for e in new}
    assert next(e for e in new if e["sku"] == "987654")["decal"] is True   # decal-driven
    assert all(e["real"] is True for e in events)                       # live => real


def test_real_catalog_sample_is_silent_when_unchanged():
    """Comparing the full catalog to ITSELF yields no events — silence at scale,
    even though the full snapshot carries on-sale + out-of-stock items."""
    prods = _load_catalog().get("products", [])
    assert len(prods) > 1000
    assert dc.detect_change(prods, prods, as_of="2026-11-18") == []


# --------------------------------------------------------------------------
# *二次 parse* — raw API fields are JSON strings
# --------------------------------------------------------------------------

def test_normalize_parses_json_string_fields():
    raw = {
        "code": "2048748",
        "name": "Charmin 衛生紙",
        "price": "{\"intValue\":999}",
        "basePrice": "{\"intValue\":1299}",
        "stock": "{\"stockLevelStatus\":\"inStock\"}",
        "decalData": [{"value": {"altText": "Costco好市多限時特價商品"}}],
        "url": "/Household/p/2048748",
    }
    n = dc.normalize_item(raw)
    assert n["sku"] == "2048748"                 # raw keys the sku "code"
    assert n["price"] == 999.0
    assert n["basePrice"] == 1299.0
    assert n["stock"] == "inStock"
    assert "Costco好市多限時特價商品" in n["decals"]


def test_detect_change_on_raw_json_string_snaps():
    prev = [{"code": "A1", "name": "x", "price": '{"intValue":1000}',
             "basePrice": '{"intValue":1000}', "stock": '{"stockLevelStatus":"inStock"}',
             "decalData": []}]
    cur = [{"code": "A1", "name": "x", "price": '{"intValue":800}',
            "basePrice": '{"intValue":1000}', "stock": '{"stockLevelStatus":"outOfStock"}',
            "decalData": [{"value": {"altText": "Costco好市多限時特價商品"}}]}]
    events = dc.detect_change(prev, cur, as_of="2026-11-18")
    kinds = {e["type"] for e in events}
    assert "price_drop" in kinds       # 800 < 1000 and newly on-sale + decal
    assert "out_of_stock" in kinds     # inStock -> outOfStock (raw JSON form)


# --------------------------------------------------------------------------
# reuse of alerts: dedup (scan) + sink (emit)
# --------------------------------------------------------------------------

def test_scan_events_reuses_alerts_dedup_and_emits():
    """scan_events dedups via alerts.alert_signature and deliver() routes through
    alerts.emit — prove both are reused, with a real=False suppression."""
    events = [
        {"type": "price_drop", "verdict": "price_drop", "sku": "100",
         "name": "A", "price": 800.0, "url": "/p/100", "as_of": "2026-11-18",
         "drop_pct": 10.0, "label": "📉 降價", "real": True},
        {"type": "price_drop", "verdict": "price_drop", "sku": "100",
         "name": "A", "price": 800.0, "url": "/p/100", "as_of": "2026-11-18",
         "drop_pct": 10.0, "label": "📉 降價", "real": True},   # duplicate -> deduped
        {"type": "out_of_stock", "verdict": "out_of_stock", "sku": "200",
         "name": "B", "price": 500.0, "url": "/p/200", "as_of": "2026-11-18",
         "drop_pct": 0.0, "label": "🔴 缺貨", "real": True},
        {"type": "price_drop", "verdict": "price_drop", "sku": "300",
         "name": "C", "price": 700.0, "url": "/p/300", "as_of": "2026-11-18",
         "drop_pct": 5.0, "label": "📉 降價", "real": False},   # fallback -> suppressed
    ]
    fresh, state = dc.scan_events(events, log_skipped=True)
    fired_skus = sorted({a["sku"] for a in fresh})
    assert fired_skus == ["100", "200"]             # dup of 100 deduped; 300 (synthetic) suppressed
    # deduped: a re-scan with the returned state yields nothing new
    again, _ = dc.scan_events(events, state=state)
    assert again == []
    # emit through alerts (log sink = the always-green path) returns the count
    n = dc.deliver(fresh, sink="log")
    assert n == 2
    # the synthetic event must never have been delivered
    assert "300" not in {a["sku"] for a in fresh}


# --------------------------------------------------------------------------
# A3 — refresh_catalog fallback (404 / 429 / conn / empty / live)
# --------------------------------------------------------------------------

def _http_error(code):
    import http.client
    req = urllib.request.Request(
        "https://www.costco.com.tw/rest/v2/taiwan/products/search")

    def _f():
        raise urllib.error.HTTPError(
            req.full_url, code, f"HTTP {code}", http.client.HTTPMessage({}), None)
    return _f


def _conn_error():
    def _f():
        raise urllib.error.URLError("connection refused")
    return _f


def _live_ok(items):
    def _f():
        return items
    return _f


def _write_snapshot(tmp_path, items):
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps({"_meta": {}, "products": items},
                            ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_fallback_on_404_returns_snapshot_and_logs(tmp_path, capsys):
    snap = [_item("100", 800.0), _item("200", 900.0)]
    snap_path = _write_snapshot(tmp_path, snap)
    res = dc.refresh_catalog(_http_error(404), snapshot_path=snap_path,
                             as_of="2026-11-18", log=True)
    assert res["source"] == "fallback"
    assert res["real"] is False
    assert res["error"].startswith("HTTP 404")
    assert [i["sku"] for i in res["items"]] == ["100", "200"]   # the snapshot
    out = capsys.readouterr().out
    assert "回退到最新快照" in out                      # the explicit fallback log
    # no alert ever fired from a fallback snapshot
    assert res["alerts"] == []


def test_fallback_does_not_overwrite_history(tmp_path):
    """The golden rule of A3: a fallback READS the snapshot, it must never touch
    history_data.json or truncate the snapshot file itself."""
    snap = [_item("100", 800.0)]
    snap_path = _write_snapshot(tmp_path, snap)
    hist_bytes = HISTORY.read_bytes()
    snap_bytes = Path(snap_path).read_bytes()
    dc.refresh_catalog(_http_error(404), snapshot_path=snap_path,
                       as_of="2026-11-18", log=False)
    assert HISTORY.read_bytes() == hist_bytes          # history untouched
    assert Path(snap_path).read_bytes() == snap_bytes   # snapshot untouched


def test_fallback_suppresses_would_be_alerts(tmp_path, capsys):
    """On a fallback we must NOT fire a false alert: even if the previous catalog
    would show a change, the (non-real) events are suppressed and only a skip
    note is logged — mirroring alerts.scan's 'log a skip note' golden rule."""
    snap = [_item("100", 800.0, base=1200.0)]   # on sale
    snap_path = _write_snapshot(tmp_path, snap)
    prev = [_item("100", 2000.0, base=1200.0)]  # prev had 2000 -> fallback shows a drop
    res = dc.refresh_catalog(_http_error(429), snapshot_path=snap_path, prev=prev,
                             as_of="2026-11-18", log=True)
    assert res["source"] == "fallback" and res["real"] is False
    assert res["alerts"] == []                       # nothing delivered
    assert res["events"]                             # changes WERE detected...
    assert res["suppressed"] >= 1                     # ...but suppressed
    out = capsys.readouterr().out
    assert "NOT delivered" in out                     # ...with a skip note


def test_fallback_on_429_uses_snapshot(tmp_path):
    snap = [_item("100", 800.0)]
    res = dc.refresh_catalog(_http_error(429), snapshot_path=_write_snapshot(tmp_path, snap),
                             as_of="2026-11-18", log=False)
    assert res["source"] == "fallback" and res["error"].startswith("HTTP 429")


def test_fallback_on_connection_error_uses_snapshot(tmp_path):
    snap = [_item("100", 800.0)]
    res = dc.refresh_catalog(_conn_error(), snapshot_path=_write_snapshot(tmp_path, snap),
                             as_of="2026-11-18", log=False)
    assert res["source"] == "fallback"
    assert res["error"].startswith("URLError")
    assert [i["sku"] for i in res["items"]] == ["100"]


def test_fallback_with_no_snapshot_is_empty_and_crashfree(tmp_path):
    res = dc.refresh_catalog(_http_error(404), snapshot_path=str(tmp_path / "nope.json"),
                             as_of="2026-11-18", log=True)
    assert res["source"] == "empty"
    assert res["real"] is False
    assert res["items"] == []                        # no snapshot -> empty, still no crash
    assert res["alerts"] == []


def test_live_success_fires_changes_with_dedup(tmp_path):
    """A real (live) fetch's changes DO fire — and a re-scan dedups them."""
    prev = [_item("100", 1000.0), _item("999", 500.0)]
    live = [_item("100", 900.0), _item("999", 500.0), _item("777", 300.0, name="新品")]
    res = dc.refresh_catalog(_live_ok(list(live)),
                             snapshot_path=_write_snapshot(tmp_path, live),
                             prev=prev, as_of="2026-11-18", log=False)
    assert res["source"] == "live" and res["real"] is True
    # 100 fell (price_drop), 777 is new (new_item); 999 unchanged -> no event at all
    kinds = {e["type"] for e in res["events"]}
    assert "price_drop" in kinds and "new_item" in kinds
    fired = {e["sku"] for e in res["events"]}
    assert "100" in fired and "777" in fired and "999" not in fired
    # dedup: the first scan fires; a second scan with that state fires nothing new
    fresh1, st1 = dc.scan_events(res["events"])
    assert {a["sku"] for a in fresh1} == {"100", "777"}
    fresh2, _ = dc.scan_events(res["events"], state=st1)
    assert fresh2 == []


def test_deliver_empty_is_noop():
    assert dc.deliver([], sink="log") == 0
    assert alerts.emit([]) == 0
