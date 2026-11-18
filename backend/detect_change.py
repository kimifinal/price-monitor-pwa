"""detect_change — Tier A of #35: Costco *item-layer* detectChange + decal
alerts + a graceful snapshot fallback.

This is the Python half of the `costco_mvm_scraper` architecture
(`pipeline/costco-mvm-scraper-v2.md § 架構`): fetchCatalog -> detectChange ->
alert -> fallback, restricted to the fully-automated item layer (no vision).

Three concerns, all OFFLINE + deterministic (CI-safe):

  A1 detectChange(prev, cur)  — diff two snapshots, emit only the *changes*:
      * price_drop   : price fell vs the previous snapshot, OR the sku just went
                       on sale (price < basePrice), OR a «限時特價 / 優惠特價»
                       decal newly appeared.
      * out_of_stock : stockLevelStatus flipped inStock -> outOfStock.
      * new_item     : a sku that wasn't in the previous snapshot, OR a
                       «網路獨家 / 新品推薦» decal newly appeared on an existing
                       sku.
      When nothing changed a sku yields NO event (silence — no false alerts).

  A2 decal signals — the three kinds above are also driven by `decals` (the full
      catalog carries them): a newly-appeared deal decal counts as a price_drop,
      a newly-appeared 網路獨家/新品推薦 decal counts as a new_item. Decal
      triggers are TRANSITIONS (a decal that was already present does not re-fire).

  A3 refresh_catalog          — pull the live catalog; on ANY failure (HTTP 404 /
      429 / connection error) fall back to the last saved snapshot WITHOUT
      overwriting history and WITHOUT firing any alert (the golden rule: a
      fallback/synthetic result is never delivered). It logs "回退到快照".

  *二次 parse* — the live API returns `price` / `basePrice` / `stock` / `decalData`
  as JSON *strings* (`"{"intValue":999}"`, `"{"stockLevelStatus":"inStock"}"`); the
  persisted `products.full.json` already carries them native. `normalize_item`
  accepts BOTH and never raises on a bad field.

Reuse, not re-implementation: alert dedup goes through `alerts.alert_signature` +
`alerts.load_state/save_state` ("notify once per event" is the same SSOT the
verdict scanner uses), and delivery goes through `alerts.emit` / `alerts.emit_log`.
"""
from __future__ import annotations

import json
import os
import urllib.error
from datetime import datetime
from typing import Optional

import alerts   # reuse the dedup + sink layer (alert_signature / emit / load_state)


# --------------------------------------------------------------------------
# decal vocabulary (A2)
#
# The full catalog's decal values look like "Costco好市多限時特價商品"; we match
# by substring so a new prefix/variant stays covered. 速配 is NOT a deal/new
# signal, so it is deliberately absent from both lists below.
# --------------------------------------------------------------------------
DEAL_DECAL_KEYS = ("限時特價", "限時特价", "優惠特价", "優惠特價")        # 降價 / 特價
NEW_DECAL_KEYS = ("網路獨家", "新品推薦")                                # 新品 / 上架

# Human labels (lead the emitted alert; the log sink prints this directly).
_LABELS = {
    "price_drop": "📉 降價",
    "out_of_stock": "🔴 缺貨",
    "new_item": "🆕 新品",
}

# Where the last saved catalog snapshot lives (git-tracked, offline-readable).
DEFAULT_CATALOG_SNAPSHOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data",
                 "costco_catalog", "products.full.json")
)


# --------------------------------------------------------------------------
# A — field parsing (the *二次 parse*)
# --------------------------------------------------------------------------
def parse_field(v):
    """Parse a possibly-JSON-stringified field. A non-JSON token (e.g. the bare
    string "inStock", or a plain number-as-string) is returned as-is; `null` /
    empty / a malformed JSON string degrade to None. Never raises."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() == "null":
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return s                      # not JSON: keep the raw token
    return v


def _num(v) -> Optional[float]:
    """Coerce a price-ish field (native number, JSON string `{"intValue":..}`,
    or a bare numeric string) to a float, or None. Never raises."""
    v = parse_field(v)
    if isinstance(v, dict):
        for k in ("intValue", "value", "amount", "price", "currencyAmount", "cent"):
            cand = v.get(k)
            if cand not in (None, ""):
                try:
                    return float(cand)
                except (TypeError, ValueError):
                    continue
        return None
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stock_status(raw: dict) -> Optional[str]:
    """Resolve a product's stock status, handling BOTH the raw API form
    (`stock` = `{"stockLevelStatus":"inStock"}`) and the normalized form
    (`stock` = "inStock", or `stock_status`). Returns the normalized status
    string, e.g. "inStock" / "outOfStock", or None."""
    if raw.get("stock_status") is not None:
        return raw["stock_status"]
    s = parse_field(raw.get("stock"))
    if isinstance(s, dict):
        return s.get("stockLevelStatus")
    return s if isinstance(s, str) else None


def decal_texts(raw: dict) -> list:
    """Flatten a product's decals to a clean list of display strings, handling
    BOTH the raw API form (`decalData: [{"value":{"altText":"速配"}}]`) and the
    normalized form (`decals: ["速配",...]`, possibly a JSON string). `null` /
    empty / junk entries are dropped so they can't masquerade as a signal."""
    val = parse_field(raw.get("decals"))
    if val is None and raw.get("decalData") is not None:
        val = raw.get("decalData")
    out: list = []
    for d in (val or []):
        text = None
        if isinstance(d, dict):
            inner = d.get("value")
            if isinstance(inner, dict):
                text = inner.get("altText") or inner.get("text") or inner.get("value")
            elif inner is not None:
                text = inner
            if text is None:
                text = d.get("altText") or d.get("text") or d.get("value")
        else:
            text = d
        if text and str(text).strip().lower() != "null":
            out.append(str(text))
    return out


def normalize_item(raw: dict) -> Optional[dict]:
    """Normalize ONE catalog item — raw API shape OR `products.full.json` shape —
    into a canonical dict the diff can reason about. Returns None for junk input.

      {sku, name, price, basePrice, discount, discount_pct, stock,
       decals(list), warehouse, url}
    """
    if not isinstance(raw, dict):
        return None
    sku = raw.get("sku")
    if sku is None:
        sku = raw.get("code")               # the raw API keys the sku "code"
    price = _num(raw.get("price"))
    base = _num(raw.get("basePrice"))

    disc = None
    if raw.get("discount") is not None:
        try:
            disc = float(raw["discount"])
        except (TypeError, ValueError):
            disc = None
    if disc is None and price is not None and base is not None:
        disc = round(base - price, 2)

    dpct = raw.get("discount_pct")
    try:
        dpct = float(dpct) if dpct is not None else None
    except (TypeError, ValueError):
        dpct = None

    return {
        "sku": str(sku) if sku is not None else None,
        "name": raw.get("name") or raw.get("englishName") or "",
        "price": price,
        "basePrice": base,
        "discount": disc,
        "discount_pct": dpct,
        "stock": stock_status(raw),
        "decals": decal_texts(raw),
        "warehouse": bool(raw.get("warehouse") or raw.get("warehouseFulfilled")),
        "online_only": bool(raw.get("online_only")),
        "url": raw.get("url"),
    }


def _is_deal_decal(d: str) -> bool:
    return any(k in d for k in DEAL_DECAL_KEYS)


def _is_new_decal(d: str) -> bool:
    return any(k in d for k in NEW_DECAL_KEYS)


# --------------------------------------------------------------------------
# A1 + A2 — the snapshot diff
# --------------------------------------------------------------------------
def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _went_out_of_stock(prev_stock, cur_stock) -> bool:
    """True only on a genuine in-stock -> out-of-stock transition. We require a
    known previous status, so an unknown prev never fires a false out_of_stock."""
    def norm(s):
        return None if s is None else s.strip().lower()
    cs, ps = norm(cur_stock), norm(prev_stock)
    return cs == "outofstock" and ps not in (None, "outofstock")


def _evt(etype: str, item: dict, as_of: str, reasons: list, drop: float,
         decal: bool, decal_added=None) -> dict:
    return {
        "type": etype,
        "verdict": etype,                  # feeds alert_signature / emit
        "sku": item["sku"],
        "name": item.get("name") or item["sku"],
        "price": item.get("price"),
        "basePrice": item.get("basePrice"),
        "url": item.get("url"),
        "currency": "TWD",
        "as_of": as_of,
        "drop_pct": round(drop, 1) if isinstance(drop, (int, float)) else 0.0,
        "reasons": list(reasons),
        "reason": "；".join(reasons),
        "decal": bool(decal),
        "decal_added": list(decal_added or []),
        "label": _LABELS[etype],
        "real": True,                      # the caller (A3) flips this on fallback
    }


def _diff_existing(p: dict, c: dict, as_of: str, decal: bool) -> list:
    """Events for a sku present in BOTH snapshots. A truly unchanged sku yields
    nothing (silence)."""
    events = []

    # ---- decal transitions (A2 signal source) ----
    prev_decals = set(p.get("decals") or [])
    cur_decals = set(c.get("decals") or [])
    added = sorted(cur_decals - prev_decals)
    deal_added = [d for d in added if _is_deal_decal(d)] if decal else []
    new_added = [d for d in added if _is_new_decal(d)] if decal else []

    # ---- price drop: a fall vs prev, a *new* on-sale, or a new deal decal ----
    pp, cp = p.get("price"), c.get("price")
    base = c.get("basePrice")
    prev_base = p.get("basePrice")
    reasons: list = []
    drops: list = []
    on_sale_now = base is not None and cp is not None and cp < base
    on_sale_prev = prev_base is not None and pp is not None and pp < prev_base
    if on_sale_now and not on_sale_prev:        # a TRANSITION into the sale
        reasons.append("特價（price < basePrice）")
        drops.append((base - cp) / base * 100.0 if base else 0.0)
    if pp is not None and cp is not None and cp < pp:
        reasons.append("price 較上次下跌")
        drops.append((pp - cp) / pp * 100.0 if pp else 0.0)
    decal_flag = False
    if deal_added:
        reasons.append("標籤新增 " + "、".join(deal_added))
        decal_flag = True
    if reasons:
        events.append(_evt("price_drop", c, as_of, reasons,
                           max(drops) if drops else 0.0,
                           decal_flag, decal_added=deal_added))

    # ---- out of stock: inStock -> outOfStock ----
    if _went_out_of_stock(p.get("stock"), c.get("stock")):
        events.append(_evt("out_of_stock", c, as_of,
                           ["庫存 由有貨轉為缺貨"], 0.0, False))

    # ---- new item via a newly-appeared 網路獨家 / 新品推薦 decal ----
    if new_added:
        events.append(_evt("new_item", c, as_of,
                           ["標籤新增 " + "、".join(new_added)], 0.0, True,
                           decal_added=new_added))

    return events


def _new_item_event(c: dict, as_of: str, decal: bool) -> Optional[dict]:
    """A sku brand-new to the catalog. Mark decal=True if it ships an
    網路獨家/新品推薦 sticker (A2 new-item signal)."""
    decal_hits = [d for d in (c.get("decals") or []) if _is_new_decal(d)] if decal else []
    reasons = []
    if decal_hits:
        reasons.append("新品：" + "、".join(decal_hits))
    else:
        reasons.append("新增 SKU")
    return _evt("new_item", c, as_of, reasons, 0.0, bool(decal_hits),
                decal_added=decal_hits)


def detect_change(prev, cur, as_of: Optional[str] = None,
                  decal: bool = True) -> list:
    """Diff two snapshots and return the list of change events (A1+A2).

    `prev` / `cur` are lists of catalog items — raw API shape OR
    `products.full.json` shape (normalize_item accepts both, and does the
    *二次 parse* of the JSON-string fields). Only skus that actually CHANGE
    produce an event; an unchanged sku is silent (no false alert).

    `as_of` is the dedup day (defaults to today); `decal=False` disables the
    decal-driven signals (pure price/stock/sku diff).
    """
    as_of = as_of or _today()
    prev_by_sku = {}
    for raw in (prev or []):
        n = normalize_item(raw)
        if n and n["sku"]:
            prev_by_sku[n["sku"]] = n

    events: list = []
    for raw in (cur or []):
        c = normalize_item(raw)
        if not c or not c["sku"]:
            continue
        p = prev_by_sku.get(c["sku"])
        if p is None:
            ev = _new_item_event(c, as_of, decal)
            if ev:
                events.append(ev)
        else:
            events.extend(_diff_existing(p, c, as_of, decal))
    return events


# --------------------------------------------------------------------------
# alert integration (reuse alerts' dedup + sink)
# --------------------------------------------------------------------------
def event_to_alert(ev: dict, as_of: Optional[str] = None) -> dict:
    """Cast a change-event to an alert dict with the exact field shape
    `alerts.alert_signature` / `alerts.emit` expect (sku, verdict, as_of,
    label, name, price, currency, drop_pct, url, threshold, at_all_time_low)."""
    return {
        "sku": ev["sku"],
        "name": ev["name"],
        "verdict": ev["verdict"],
        "label": ev["label"],
        "drop_pct": ev.get("drop_pct", 0.0),
        "price": ev.get("price"),
        "currency": ev.get("currency", "TWD"),
        "url": ev.get("url"),
        "as_of": as_of or ev.get("as_of") or _today(),
        "threshold": None,
        "at_all_time_low": False,
        "type": ev["type"],
        "decal": ev.get("decal", False),
        "reason": ev.get("reason", ""),
        "real": ev.get("real", True),
    }


def scan_events(events, state: Optional[dict] = None,
                policy: Optional[dict] = None,
                log_skipped: bool = False):
    """Dedup change-events to a 'fire once per event' set, REUSING
    `alerts.alert_signature` + the state SSOT `alerts.save_state` writes.

    Returns (fresh_alerts, updated_state). Golden rule (the same as
    `alerts.scan`): an event flagged `real=False` (a fallback / synthetic
    snapshot, A3) is NEVER delivered; with `log_skipped` we print a skip note
    instead, so a fallback pipeline can see *what* it would have said without
    emitting a false shout. `policy` may narrow via a `types` whitelist."""
    state = dict(state or {})
    allowed = set((policy or {}).get(
        "types", {"price_drop", "out_of_stock", "new_item"}))
    fresh: list = []
    skipped = 0
    for ev in events:
        a = event_to_alert(ev)
        if a["verdict"] not in allowed:
            continue
        if not a.get("real", True):       # golden rule: never deliver fallback data
            if log_skipped:
                skipped += 1
            continue
        sig = alerts.alert_signature(a)    # reuse the verdict scanner's dedup key
        sigs = state.setdefault(a["sku"], [])
        if sig in sigs:
            continue
        sigs.append(sig)
        a["sig"] = sig
        fresh.append(a)
    if log_skipped and skipped:
        print(f"[detect_change:skip] {skipped} fallback/synthetic event(s) "
              f"would alert — NOT delivered (golden rule：no false shouts on "
              f"non-real data)")
    return fresh, state


def deliver(alerts_list, sink: str = "log", token: str = "",
            http_post=None) -> int:
    """Deliver change-alerts through `alerts.emit` (sink: log / telegram / github).
    The dedup that keeps an event from firing twice lives upstream in
    `scan_events`; this just routes the ALREADY-deduped batch."""
    if not alerts_list:
        return 0
    return alerts.emit(alerts_list, sink=sink, token=token, http_post=http_post)


# --------------------------------------------------------------------------
# A3 — graceful fallback when the live catalog fetch fails
# --------------------------------------------------------------------------
def load_catalog_snapshot(path: Optional[str] = None):
    """Read the last saved catalog snapshot. Returns (items, ok). Offline, never
    raises — a missing / corrupt / non-list snapshot yields ([], False)."""
    p = path or DEFAULT_CATALOG_SNAPSHOT
    if not os.path.exists(p):
        return [], False
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return [], False
    items = data.get("products") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return [], False
    return items, True


def refresh_catalog(live_fetch, snapshot_path: Optional[str] = None,
                    prev=None, as_of: Optional[str] = None,
                    log: bool = True) -> dict:
    """A3: pull the live catalog; on ANY failure fall back to the last saved
    snapshot — WITHOUT overwriting history and WITHOUT firing a false alert.

    `live_fetch` is a zero-arg callable the caller injects (a mock in tests, the
    real HTTP pull in production); this stays 100% offline because tests pass a
    fake. `snapshot_path` is the fallback source (default: the tracked
    `data/costco_catalog/products.full.json`).

    Returns a result dict:
        {items, source, real, error, snapshot_path, as_of, events, alerts,
         suppressed}
      * source: 'live' | 'fallback' | 'empty'
      * real:   True ONLY for a successful LIVE fetch
      * events: detect_change(prev, items) if a prev is supplied (so a caller can
                diff a fallback against the last good catalog)
      * alerts: deliverable alerts — ALWAYS [] when source != 'live' (a fallback
                snapshot is marked non-real and suppressed by `scan_events`; the
                golden rule)
      * suppressed: how many events `scan_events` *would* have fired on non-real
                   data (the skip-note count, when log=True)
      * NOTE: the function NEVER writes to snapshot_path or history_data.json.
    """
    as_of = as_of or _today()
    items = None
    err = None
    try:
        items = live_fetch()
    except urllib.error.HTTPError as e:
        err = f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        err = f"{type(e).__name__}: {e}"
    except Exception as e:
        err = f"{type(e).__name__}"

    result = {
        "items": items if items else [],
        "source": "live" if err is None and items else "empty",
        "real": err is None and bool(items),
        "error": err,
        "snapshot_path": snapshot_path,
        "as_of": as_of,
        "events": [],
        "alerts": [],
        "suppressed": 0,
    }

    if result["real"]:
        if log:
            print(f"[detect_change] live catalog: {len(result['items'])} 筆 "
                  f"@ {as_of}")
    else:
        snap, ok = load_catalog_snapshot(snapshot_path)
        result["items"] = snap
        result["source"] = "fallback" if ok else "empty"
        if ok:
            if log:
                print(f"[detect_change] 抓取失敗（{err}）→ 回退到最新快照 "
                      f"（{len(snap)} 筆，{snapshot_path or DEFAULT_CATALOG_SNAPSHOT}）；"
                      f"不覆寫歷史、不發假警報")
        else:
            if log:
                print(f"[detect_change] 抓取失敗（{err}），且無可用快照 → 回傳空快照；"
                      f"不覆寫歷史、不發假警報")

    # Detect changes vs the previous catalog, but suppress delivery on a
    # non-live result (golden rule). scan_events flips real=False events out.
    if prev and result["items"]:
        events = detect_change(prev, result["items"], as_of=as_of)
        for ev in events:
            ev["real"] = result["real"]
        result["events"] = events
        fresh, _state = scan_events(events, log_skipped=(log and not result["real"]))
        result["alerts"] = fresh if result["real"] else []
        result["suppressed"] = len(events) - len(fresh) if not result["real"] else 0

    return result
