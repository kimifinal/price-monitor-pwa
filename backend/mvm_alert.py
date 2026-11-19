"""mvm_alert — Tier B3 of #35: fire MVM 檔期 alerts, reusing the Tier A core.

Two MVM signals become alerts:

  * a **new MVM 檔期** appeared  — detected by B1 `mvm_detect.detect_new_tabs`
    (a content url / tab_id absent from the tracked manifest),
  * a **MVM price drop** — a product whose `promo` fell vs the previous snapshot,
    detected by REUSING Tier A `detect_change.detect_change` (it emits a
    `price_drop` event).

Everything heavy is REUSED, not re-implemented (§ "dedup/sink 照搬 Tier A"):
  * new-tab alerts dedup through `alerts.alert_signature` + emit through
    `alerts.emit` / `alerts.emit_log` (the SAME verdict dedup + sink the item
    layer uses),
  * price-drop alerts flow through `detect_change.scan_events` (its dedup + the
    golden-rule "never fire on non-real / fallback data") and
    `detect_change.deliver` (which routes to `alerts.emit`).

Golden rule (a hard inherited AC): a fallback / non-real snapshot NEVER fires a
false alarm.  `fallback` (no previous snapshot) degrades to "no crash, no
price-drop alert" — a brand-new snapshot only reveals `new_item` changes, which
we deliberately do NOT alert on here.  Silence: when nothing new/changed, no
alert is emitted.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import alerts              # reuse the dedup (alert_signature) + sink (emit / emit_log)
import detect_change as dc  # reuse the change diff + its dedup layer (scan_events / deliver)
import mvm_detect

# A new MVM 檔期 is its own verdict (distinct from the item-layer verdicts) so its
# dedup signature can never collide with a price/out_of_stock/new_item alert.
NEW_MVMTAB_VERDICT = "new_mvm_tab"
NEW_MVMTAB_LABEL = "🆕 新 MVM 檔期"
DROP_VERDICT = "price_drop"                 # the verdict dc detects_change emits


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# signal 1 — new MVM tab  (reuse B1)
# --------------------------------------------------------------------------
def mvm_new_tab_alert(tab_id: str, observed_tabs, manifest: Optional[dict] = None,
                      as_of: Optional[str] = None) -> dict:
    """One new-tab -> an alert dict in the exact shape
    `alerts.alert_signature` / `alerts.emit` expect.  `url` / `name` come from
    `mvm_detect.describe_new_tab` (a new tab isn't in the manifest, so we
    reconstruct the best we can and never crash)."""
    info = mvm_detect.describe_new_tab(tab_id, observed_tabs, manifest)
    return {
        "sku": str(tab_id),                  # the tab IS the dedup identity
        "tab_id": str(tab_id),
        "name": info.get("label", f"新 MVM 檔期 {tab_id}"),
        "verdict": NEW_MVMTAB_VERDICT,
        "label": NEW_MVMTAB_LABEL,
        "drop_pct": 0.0,
        "price": None,
        "currency": None,
        "url": info.get("url"),
        "as_of": as_of or _today(),
        "threshold": None,
        "at_all_time_low": False,
        "type": NEW_MVMTAB_VERDICT,
        "real": True,
    }


def new_tab_alerts(observed_tabs, manifest: Optional[dict] = None,
                   as_of: Optional[str] = None) -> list:
    """All new MVM tabs from `observed_tabs` vs `manifest`, each as an alert dict.
    REUSES B1 `detect_new_tabs` for the detection; feeds empty => empty."""
    as_of = as_of or _today()
    out = []
    for tab_id in mvm_detect.detect_new_tabs(observed_tabs, manifest):
        out.append(mvm_new_tab_alert(tab_id, observed_tabs, manifest, as_of=as_of))
    return out


# --------------------------------------------------------------------------
# signal 2 — MVM price drop  (reuse Tier A detect_change)
# --------------------------------------------------------------------------
def _dc_item(p: dict) -> dict:
    """Adapt a MVM product (promo/orig) to the shape Tier A's `detect_change`
    expects (`price`=promo, `basePrice`=orig), so we REUSE the shared diff.
    This is a 3-line adapter; the heavy diff/dedup/sink is all in `detect_change`."""
    p = p or {}
    sku = p.get("sku")
    return {
        "sku": str(sku) if sku not in (None, "") else None,
        "name": p.get("name"),
        "price": p.get("promo"),
        "basePrice": p.get("orig"),
        "url": None,
        "decals": [],
    }


def _flatten_products(catalog) -> list:
    """Flatten any MVM catalog shape to a product list:
      * p4.json dict {tabs:[{products:[...]}]}
      * {tab_id: [products]}
      * a single product dict
      * a flat product list
    None / junk degrades to [] (fallback-safe)."""
    if catalog is None:
        return []
    if isinstance(catalog, dict):
        if "tabs" in catalog:
            out: list = []
            for t in (catalog.get("tabs") or []):
                t = t or {}
                out.extend(t.get("products") or [])
            return out
        if catalog and all(isinstance(v, list) for v in catalog.values()):
            return [p for v in catalog.values() for p in v]
        return [catalog]                       # a single product
    if isinstance(catalog, list):
        return list(catalog)
    return []


def price_drop_alerts(prev_catalog, cur_catalog, as_of: Optional[str] = None) -> list:
    """MVM `price_drop` alerts by REUSING `detect_change.detect_change` on the
    flattened product lists, casting each event via
    `detect_change.event_to_alert`.  A snapshot with no `prev` yields only
    `new_item` events (not price drops) => [] here, so a fallback can't shout a
    false "price dropped".  `out_of_stock` / `new_item` are filtered out — MVM
    alerts are new-tab + price-drop only."""
    prev = [_dc_item(p) for p in _flatten_products(prev_catalog)]
    cur = [_dc_item(p) for p in _flatten_products(cur_catalog)]
    events = dc.detect_change(prev, cur, as_of=as_of or _today())
    out = []
    for e in events:
        if e.get("verdict") == DROP_VERDICT and e.get("real", True):
            a = dc.event_to_alert(e, as_of=as_of or _today())
            out.append(a)
    return out


# --------------------------------------------------------------------------
# unified scan — dedup + sink  (reuse alerts.alert_signature + alerts.emit)
# --------------------------------------------------------------------------
def scan_mvm(prev_catalog, cur_catalog, observed_tabs, manifest: Optional[dict] = None,
             as_of: Optional[str] = None, state: Optional[dict] = None,
             sink: str = "log", token: str = "", http_post=None,
             log_skipped: bool = False) -> dict:
    """Decide which MVM alerts to fire *now* and DELIVER them through the Tier A
    sink, sharing ONE dedup `state` across the two signals.

    Returns a result dict:
      {new_tabs, new_tab_alerts, price_drop_alerts, price_drop_events,
       alerts (all fresh), delivered, state, sources}

    Fallback rules (inherited golden rule):
      * no `manifest` / no new tab  -> no new-tab alerts,
      * no `prev_catalog` (fallback) -> no price-drop alert (a fresh snapshot only
        shows new items, which we do not alert on) — so we never crash and never
        fire a false "price dropped",
      * nothing new / changed        -> `alerts` is [] and `delivered == 0`
        (silence, no false alert).
    """
    as_of = as_of or _today()
    state = dict(state or {})

    # ---- signal 1: new MVM tabs (B1), deduped through alerts.alert_signature ----
    new_tab_ids = mvm_detect.detect_new_tabs(observed_tabs, manifest)
    fresh_new: list = []
    for a in new_tab_alerts(observed_tabs, manifest, as_of=as_of):
        sig = alerts.alert_signature(a)          # reuse the verdict dedup key
        sigs = state.setdefault(a["sku"], [])
        if sig in sigs:
            continue
        sigs.append(sig)
        a["sig"] = sig
        fresh_new.append(a)

    # ---- signal 2: MVM price drops (reuse detect_change.scan_events + emit) ----
    fresh_drops: list = []
    events = drops_as_events(prev_catalog, cur_catalog, as_of)
    if events:
        # REUSE Tier A's dedup layer (detect_change.scan_events) over the shared
        # state; scan_events already routes through event_to_alert + the golden
        # rule (non-real/fallback events are suppressed, never delivered).
        fresh_drops, state = dc.scan_events(events, state,
                                            policy={"types": {DROP_VERDICT}})

    all_fresh = fresh_new + fresh_drops
    delivered = alerts.emit(all_fresh, sink=sink, token=token, http_post=http_post) \
        if all_fresh else 0

    return {
        "new_tabs": new_tab_ids,
        "new_tab_alerts": fresh_new,
        "price_drop_alerts": fresh_drops,
        "alerts": all_fresh,
        "delivered": delivered,
        "state": state,
        "sources": "mvm-vision(tier-b)",
    }


def drops_as_events(prev_catalog, cur_catalog, as_of: Optional[str] = None) -> list:
    """The raw `price_drop` change-events (pre-alert) for `detect_change.scan_events`
    to dedup — the single point where MVM products re-enter Tier A's diff."""
    prev = [_dc_item(p) for p in _flatten_products(prev_catalog)]
    cur = [_dc_item(p) for p in _flatten_products(cur_catalog)]
    events = dc.detect_change(prev, cur, as_of=as_of or _today())
    return [e for e in events if e.get("verdict") == DROP_VERDICT]


def run_mvm_alert(prev_catalog, cur_catalog, observed_tabs, manifest: Optional[dict] = None,
                  as_of: Optional[str] = None, sink: str = "log", token: str = "",
                  http_post=None, state_path: Optional[str] = None) -> int:
    """Convenience wrapper: load a durable dedup state when `state_path` is given,
    run `scan_mvm` through `sink`, persist the state, and return the number of
    alerts actually delivered.  Offline + CI-safe (the `log` sink never raises)."""
    state = alerts.load_state(state_path) if state_path else {}
    res = scan_mvm(prev_catalog, cur_catalog, observed_tabs, manifest,
                   as_of=as_of, state=state, sink=sink, token=token, http_post=http_post)
    if state_path:
        alerts.save_state(res["state"], state_path)
    return res["delivered"]
