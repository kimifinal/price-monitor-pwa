"""mvm_detect — Tier B1 of #35: detect a *new MVM tab* appearing.

This is the offline half of the `costco_mvm_scraper` vision tier
(`pipeline/tier-b-mvm-vision.md § B1`).  MVM 檔期內容 公開 API 一律
AccessDenied (實證見 §分工), so the only observable signal of "a new 檔期
opened" is that a NEW content-url (a new tab) showed up in the listing.  We do
NOT *predict* the next 檔期 — there is no public signal (§分工 2026-11-17) — we
only detect, against the tracked manifest, that an *already-observed* url is
new (i.e. its tab_id is not in the known set).

  detect_new_tabs(observed_tab_urls, manifest) -> [new tab_ids]

The diff is by tab_id: a content url maps to `content/{tab_id}` (the manifest's
first tab carries the canonical url; the rest are derived from tab_id).  An
observed url is "new" iff its tab_id is absent from `manifest["tabs"]`.  Feeding
only the known urls yields silence (no false alarms).

Reuse: this module is pure stdlib (no alert/dedup surface — it only *detects*),
so B3 routes its output through the Tier A `detect_change` + `alerts` dedup/sink
layer (see mvm_alert.py).  It never re-implements dedup.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse

# Default content base. The manifest's first tab carries the canonical url; when
# it is absent we fall back to this, so a partial manifest still resolves tabs.
DEFAULT_CONTENT_BASE = "https://www.costco.com.tw/content/"

# Where the tracked MVM tab manifest lives (git-tracked, offline-readable).
DEFAULT_MANIFEST = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "costco_mvm",
                 "manifest.json")
)


# --------------------------------------------------------------------------
# url <-> tab_id helpers
# --------------------------------------------------------------------------
def tab_id_from_url(url: str) -> Optional[str]:
    """The trailing `{tab_id}` of a content url (or a bare tab id string).

    Robust to query strings / fragments / trailing slashes.  A value with no
    extractable segment returns None (so junk input can't masquerade as a tab)."""
    if not url or not isinstance(url, str):
        return None
    s = url.strip()
    if not s:
        return None
    # A bare id (no scheme, no slash) is itself the tab id.
    if all(c in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
           for c in s) and "/" not in s.replace("\\", ""):
        return s
    path = urlparse(s).path
    # strip a trailing slash, then take the last non-empty segment
    segs = [seg for seg in path.strip("/").split("/") if seg]
    return segs[-1] if segs else None


def content_base(manifest: Optional[dict], default: str = DEFAULT_CONTENT_BASE) -> str:
    """Resolve the `content/` base url.  Prefer the manifest's own url (top-level,
    then the first tab that carries one); fall back to `default`."""
    if not manifest:
        return default
    for src in (manifest.get("url"),
                next((t.get("url") for t in manifest.get("tabs", []) if t.get("url")), None)):
        if src and isinstance(src, str):
            base = src.rsplit("/", 1)[0] + "/"
            return base
    return default


def tab_url(manifest: Optional[dict], tab_id: str, base: Optional[str] = None) -> str:
    """Reconstruct a tab's full content url: the manifest's explicit url when
    present, else `base/{tab_id}`."""
    base = base or content_base(manifest)
    if manifest:
        for t in manifest.get("tabs", []):
            if t.get("tab_id") == tab_id and t.get("url"):
                return t["url"]
    return base + tab_id


def known_tab_ids(manifest: Optional[dict]) -> set:
    """The set of tab_ids the manifest already knows — the "known" baseline."""
    if not manifest:
        return set()
    ids = set()
    for t in manifest.get("tabs", []):
        tid = t.get("tab_id")
        if tid:
            ids.add(str(tid))
    return ids


# --------------------------------------------------------------------------
# B1 — the new-tab detector
# --------------------------------------------------------------------------
def detect_new_tabs(observed_tab_urls, manifest: Optional[dict]) -> list:
    """Return the tab_ids of tabs observed in `observed_tab_urls` that are NOT in
    `manifest["tabs"]` — i.e. newly-appeared MVM 檔期.

    `observed_tab_urls` is a list of content urls (or bare tab ids).  Each maps to
    a tab_id via `tab_id_from_url`; a tab_id absent from the manifest's known set
    is reported as new.  New tab_ids are de-duplicated and returned in
    first-seen order.

    Golden rule (silence): feeding only the manifest's own urls returns `[]` — no
    false alert.  When the manifest has no tabs (no baseline), we also return `[]`
    rather than claiming "everything is new": a diff against nothing is undefined
    and a false alarm is worse than a missed one.
    """
    known = known_tab_ids(manifest)
    if not known:                      # no manifest / no tabs -> no baseline, stay silent
        return []
    if not observed_tab_urls:
        return []

    new: list = []
    seen: set = set()
    for raw in observed_tab_urls:
        tid = tab_id_from_url(raw)
        if not tid:
            continue
        if str(tid) in known or str(tid) in seen:
            continue
        seen.add(str(tid))
        new.append(str(tid))
    return new


# --------------------------------------------------------------------------
# small helpers B3 reuses to turn a detected tab into an alert
# --------------------------------------------------------------------------
def describe_new_tab(tab_id: str, observed_tab_urls, manifest: Optional[dict]) -> dict:
    """Best-effort descriptor for a newly-detected tab, for B3 to build an alert.
    Unknown fields fall back to the tab_id itself (a new tab won't be in the
    manifest, so we reconstruct what we can and never crash)."""
    import json as _json  # lazy: only used by load_manifest, keeps import side-effect free
    url = tab_url(manifest, tab_id) if manifest else content_base(manifest) + tab_id
    # if we actually SAW the url in the observed list, prefer that exact string
    obs = _first_observed(observed_tab_urls, tab_id)
    if obs:
        url = obs
    return {
        "tab_id": str(tab_id),
        "url": url,
        "label": "新 MVM 檔期" + (f" {tab_id}" if tab_id else ""),
    }


def _first_observed(observed_tab_urls, tab_id: str) -> Optional[str]:
    for raw in (observed_tab_urls or []):
        if tab_id_from_url(raw) == str(tab_id):
            return raw if isinstance(raw, str) else None
    return None


def load_manifest(path: Optional[str] = None) -> dict:
    """Read the tracked tab manifest. Offline, never raises: a missing / corrupt /
    non-dict file degrades to `{}` (=> no baseline => silent)."""
    import json
    p = path or DEFAULT_MANIFEST
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
