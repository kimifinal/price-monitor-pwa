"""mvm_vision — Tier B2 of #35: extract MVM 檔期 prices via **vision** (offline).

MVM 檔期內容 的公開 API 一律 AccessDenied (§分工, 實測 2026-11-17), so the price
layer is extracted by VISION: screenshot each MVM tab into tiles, let a vision
model read each tile into a product, assemble the tiles into the `p4.json`
schema, and — crucially — only spend vision calls on **new / changed** skus.

Everything here is OFFLINE + deterministic for CI:

  * `VisionFn` is an *injectable* protocol — `call(tile_path, schema) ->
    {sku,name,orig,promo,discount,type,cat}`.  Production injects the real
    Playwright+LLM provider; the tests inject a `SpyVision`.  No real vision /
    Playwright is ever imported at module load, so CI stays air-gapped.
  * `tile_screenshot(image_path, tile_h=600)` is pure coordinate MATH (a
    synthesised long image is enough to test it); the image-height reader is an
    injectable `opener`, defaulting to a stdlib `struct` PNG-IHDR read (NO third
    -party image dep in CI).
  * `parse_and_assemble(tile_results, manifest)` groups tile outputs into the
    `p4.json` schema (`{tabs:[{...products[]}], price_types:{...}}`).
  * `cost_control` REUSES Tier A `detect_change.detect_change` to decide which
    skus are new/changed; an **unchanged** sku does NOT spend a vision call
    (the spy asserts the call count).

The real vision provider (`build_real_vision_provider`, `MVM_VISION_PROVIDER`
env + Playwright screenshots + an LLM vision call) is **documented but
out-of-CI** — it is never imported or constructed by the test suite.
"""
from __future__ import annotations

import os
import struct
from typing import Protocol, Optional, runtime_checkable

import detect_change as dc   # reuse Tier A's diff for cost_control (no re-implementation)


# --------------------------------------------------------------------------
# the injectable vision function
# --------------------------------------------------------------------------
@runtime_checkable
class VisionFn(Protocol):
    """Injectable vision model: one MVM tile path + the product schema -> a
    normalized product dict.  Production impls wrap Playwright + an LLM vision
    call; tests pass a spy.  `schema` describes the expected product fields."""

    def call(self, tile_path: str, schema: Optional[dict]) -> dict:
        ...


# The 7 canonical fields the schema requires (p4.json product shape).
SCHEMA = {
    "sku": "str", "name": "str", "orig": "num", "promo": "num",
    "discount": "num", "type": "str", "cat": "str",
}
_PRODUCT_FIELDS = ("sku", "name", "orig", "promo", "discount", "type", "cat")

# The canonical 3 price types (p4.json top-level `price_types`).
DEFAULT_PRICE_TYPES = {
    "online_only": {
        "label": "僅限好市多線上購物", "badge": "橙色購物車圖示",
        "meaning": "只有線上賣 賣場 沒有 或 賣場 售價 更高",
    },
    "store_online_diff": {
        "label": "賣場售價 / 線上亦有優惠",
        "badge": "橙色 '【賣場售價】' 標 + '線上購物亦有優惠 售價以官網為準'",
        "meaning": "這個價格 是賣場 的  線上 還 有 更 低 的 價",
    },
    "store_only": {
        "label": "賣場獨家 / 平日限定", "badge": "無  線上  標籤",
        "meaning": "只有 賣場  有  沒有  線上",
    },
}


# Per-tab `price_type` for the KNOWN 檔期 (the 6 tracked tabs), mirrored from the
# captured p4.json SSOT.  The manifest is *intentionally sparse* on per-tab
# metadata — its own `method` note says prices are "未 vision、需手動" — so when a
# known tab omits `price_type` we fill that gap here instead of leaving it blank.
# A tab absent from this map (a genuinely new 檔期) simply gets price_type=None.
DEFAULT_TAB_PRICE_TYPES = {
    "fy27p3-mvm2-weekday": "store_only",
    "fy27p3-mvm2-w1": "online_online_diff",
    "fy27p4-mvm2-cyber": "online_only",
    "fy27p4-mvm2-weekday": "store_only",
    "fy27p4-mvm2-w2": "online_online_diff",
}


# --------------------------------------------------------------------------
# tile coordinate math (offline)
# --------------------------------------------------------------------------
def tile_coords(height, tile_h: int = 600):
    """Pure slicing: cut a long image of `height` px into non-overlapping
    `tile_h`-px tiles.  Returns [(idx, y0, y1), ...].  ceil division, so a
    600px image -> 1 tile, 601px -> 2 tiles; the last tile may be short.  A
    non-positive height / tile_h yields `[]` (never crashes)."""
    h = int(height) if height else 0
    th = int(tile_h) if tile_h else 0            # guard None / 0 tile_h (never crash)
    if h <= 0 or th <= 0:
        return []
    n = -(-h // th)                       # ceil(h / tile_h)
    return [(i, i * th, min((i + 1) * th, h)) for i in range(n)]


def _read_png_height(path: str) -> int:
    """Read a PNG's pixel height from its IHDR chunk — stdlib `struct` only, NO
    third-party image library (so it's CI-safe).  Raises on a non-PNG path;
    callers that don't have a real png simply pass `height=` instead."""
    try:
        with open(path, "rb") as f:
            head = f.read(26)
    except OSError as exc:
        # A missing / unreadable path is a *clear error*, not a raw crash: offline
        # CI never decodes pixels, so the caller is told exactly what to inject.
        raise ValueError(
            f"no offline image height for {path!r}: pass height= or an injectable "
            f"opener= (CI never decodes pixels). {type(exc).__name__}: {exc}"
        ) from exc
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    # signature(8) + length(4) + "IHDR"(4) + width(4) + height(4): the height is
    # the last 4 of the first 26 bytes.
    width, height = struct.unpack(">II", head[16:24])
    return int(height)


def tile_screenshot(image_path, tile_h: int = 600, height: Optional[int] = None,
                    opener=None, out_dir: Optional[str] = None) -> list:
    """Return the concrete tile file paths for `image_path`, sliced into
    `tile_h`-px tiles.  The image height comes from `height` (a synthesised
    image in the tests) or an injectable `opener(image_path) -> int` (default:
    the stdlib png-IHDR reader).  This NEVER decodes pixels / never imports an
    image lib, so it is fully offline; CI passes `height=`.

    `tile_coords` is the math; this just maps coords onto sibling `png` paths."""
    if height is None:
        opener = opener or _read_png_height
        height = opener(image_path)
    coords = tile_coords(height, tile_h)
    base = out_dir or os.path.dirname(os.path.abspath(image_path)) or "."
    stem = os.path.splitext(os.path.basename(image_path))[0]
    return [os.path.join(base, f"{stem}__tile_{i:03d}.png") for (i, y0, y1) in coords]


# --------------------------------------------------------------------------
# product normalization (p4.json shape)
# --------------------------------------------------------------------------
def _to_num(v):
    try:
        if isinstance(v, bool) or v is None:
            return v
        if isinstance(v, (int, float)):
            return float(v) if isinstance(v, float) else v
        s = str(v).strip()
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def normalize_mvm_product(p: dict) -> Optional[dict]:
    """Coerce ONE vision output into the canonical 7-field product.  Jumps junk
    (no sku AND no name) to None so it can't pollute a tab."""
    if not isinstance(p, dict):
        return None
    sku = p.get("sku")
    sku = str(sku) if sku not in (None, "") else None
    name = p.get("name") or p.get("englishName") or ""
    if sku is None and not name:
        return None
    typ = p.get("type")
    if isinstance(typ, str) and typ.strip().lower() in ("null", ""):
        typ = None
    cat = p.get("cat")
    if isinstance(cat, str) and cat.strip().lower() == "null":
        cat = None
    out = {f: p.get(f) for f in _PRODUCT_FIELDS}
    out["sku"] = sku
    out["name"] = str(name)
    out["orig"] = _to_num(p.get("orig"))
    out["promo"] = _to_num(p.get("promo"))
    out["discount"] = _to_num(p.get("discount"))
    out["type"] = typ
    out["cat"] = str(cat) if cat is not None else None
    # Preserve tab_id (when present & non-empty) so per-tab assembly can group by
    # it.  It is stripped AGAIN at the tail of parse_and_assemble, so it never
    # leaks into a final p4.json product — assembly only borrows it transiently.
    tab_id = p.get("tab_id")
    if tab_id not in (None, ""):
        out["tab_id"] = str(tab_id)
    return out


def _sku_of(p: dict) -> Optional[str]:
    """The sku key used for dedup / cost-control matching (str, or None)."""
    if not isinstance(p, dict):
        return None
    sku = p.get("sku")
    return str(sku) if sku not in (None, "") else None


# --------------------------------------------------------------------------
# p4.json assembly
# --------------------------------------------------------------------------
def _flatten_products(tile_results) -> list:
    """Flatten the vision output into a list of normalized products, each tagged
    with a `tab_id`.  Accepts three shapes, in priority order:
      * a *batch* record `{tab_id, products: [...]}` (or `product: {...}`),
      * a bare product dict that already carries `tab_id`,
      * a dict with neither `product(s)` nor `sku`/`name` (skipped)."""
    out: list = []
    for item in (tile_results or []):
        if not isinstance(item, dict):
            continue
        if "products" in item or "product" in item:
            tab = item.get("tab_id")
            prods = item.get("products")
            if prods is None:
                prods = [item.get("product")]
            for p in prods:
                if p is None:
                    continue
                p = dict(p)
                p.setdefault("tab_id", tab)
                n = normalize_mvm_product(p)
                if n:
                    out.append(n)
        else:
            n = normalize_mvm_product(item)
            if n:
                out.append(n)
    return out


def _tab_order(tab_ids_seen, manifest: dict) -> list:
    """Deterministic tab order: manifest's tabs first (their declared order),
    then any tab_id seen only in the tile results, sorted (a new tab has no
    manifest position, so append it stably)."""
    order: list = []
    seen = set()
    for t in ((manifest or {}).get("tabs") or []):
        tid = t.get("tab_id")
        if tid:
            order.append(str(tid))
            seen.add(str(tid))
    for tid in sorted({str(x) for x in tab_ids_seen if x not in (None, "")} - seen):
        order.append(tid)
    return order


def parse_and_assemble(tile_results, manifest: dict,
                       price_types: Optional[dict] = None) -> dict:
    """Group tile/vision outputs into the `p4.json` schema.

    `tile_results` is any of the shapes `_flatten_products` accepts (per-tile
    products, per-tab batches, or a flat tag-less list).  `manifest` supplies the
    per-tab metadata (label / period / url / price_type / description) and tab
    ordering.  Returns `{"tabs": [...], "price_types": {...}}` where each tab
    carries `products` (deduped by sku, last-wins) and `n_products == len(products)`.
    """
    products = _flatten_products(tile_results)
    by_tab: dict = {}
    for p in products:
        tid = str(p.get("tab_id")) if p.get("tab_id") not in (None, "") else None
        by_tab.setdefault(tid or "__untagged__", []).append((p.get("sku"), p))

    manifest = manifest or {}
    tabs_out: list = []
    for tid in _tab_order((p.get("tab_id") for p in products), manifest):
        bucket = by_tab.get(tid) or by_tab.get(str(tid), [])
        # dedup by sku, last write wins (a later tile refines an earlier read)
        merged: dict = {}
        for sku, p in bucket:
            key = str(sku) if sku not in (None, "") else None
            merged[key if key is not None else f"__noname_{id(p)}__"] = p
        prods = sorted(merged.values(), key=lambda p: (p.get("sku") or "", ))
        # tab metadata: from manifest when present, else synthesised for a new tab
        meta = next((t for t in manifest.get("tabs", []) if str(t.get("tab_id")) == str(tid)), None)
        if meta:
            tab = {k: meta.get(k) for k in
                   ("tab_id", "label", "period", "url", "price_type", "description")}
            # A known tab may leave url / price_type blank (the manifest is
            # intentionally sparse).  Fill the gap so assembly stays schema-faithful:
            # url is derived as content/{tab_id}; price_type from the captured 6-檔期
            # mirror (the manifest note: per-tab prices are "未 vision、需手動").
            if not tab.get("url"):
                import mvm_detect
                tab["url"] = mvm_detect.tab_url(manifest, tid)
            if not tab.get("price_type"):
                tab["price_type"] = DEFAULT_TAB_PRICE_TYPES.get(str(tid))
        else:
            import mvm_detect
            tab = mvm_detect.describe_new_tab(tid, None, manifest)
            tab["period"] = None
            tab["price_type"] = DEFAULT_TAB_PRICE_TYPES.get(str(tid))
            tab["description"] = None
        tab["tab_id"] = str(tid)
        for p in prods:                       # strip transient tab_id from the product
            p.pop("tab_id", None)
        tab["products"] = prods
        tab["n_products"] = len(prods)
        tabs_out.append(tab)

    if price_types is None:
        price_types = (manifest or {}).get("price_types") or DEFAULT_PRICE_TYPES
    return {"tabs": tabs_out, "price_types": dict(price_types)}


# --------------------------------------------------------------------------
# cost_control — only spend vision on new / changed skus (reuse Tier A diff)
# --------------------------------------------------------------------------
def _to_dc_item(p: dict) -> dict:
    """Adapt a normalized MVM product to the shape Tier A's `detect_change`
    expects (`price` = promo, `basePrice` = orig) so we can REUSE its diff."""
    p = p or {}
    return {
        "sku": _sku_of(p),
        "name": p.get("name"),
        "price": p.get("promo"),
        "basePrice": p.get("orig"),
        "url": None,
        "decals": [],
    }


def _dedup_by_sku(items):
    """Collapse a product list to ONE entry per sku — last-wins value, first-seen
    order.  No-sku items each keep their own slot (they can't be matched, so they
    always spend a vision call).

    Why this matters: an MVM tab can list the SAME sku twice at *different* prices
    (the captured `2026-11-16_mvm_p4.json` w1 tab does).  Tier A's `detect_change`
    builds `prev_by_sku` last-wins but then diffs EVERY current occurrence, so a
    snapshot diffed against *itself* would emit spurious `price_drop` events for a
    sku's own duplicate — which would make "an unchanged sku never spends a vision
    call" FALSE.  Collapsing both snapshots by sku first makes a self-diff empty,
    the precondition for the cost-control guarantee."""
    out = []
    pos: dict = {}
    for i, it in enumerate(items or []):
        k = _sku_of(it)
        key = k if k is not None else f"__nonsku_{i}__"
        if key in pos:
            out[pos[key]] = (key, it)      # last-wins value, keep first-seen slot
        else:
            pos[key] = len(out)
            out.append((key, it))
    return out


def run_vision_with_cost_control(prev, observed, vision, schema: Optional[dict] = None,
                                 as_of: Optional[str] = None):
    """Run vision on the MVM tiles in `observed`, but ONLY for skus that are NEW
    or CHANGED vs `prev` — unchanged skus are skipped (cost control).  The
    new/changed test REUSES Tier A `detect_change` (its event set == the
    changed-or-new skus; an unchanged sku produces no event).

    `prev` / `observed` are lists of MVM product dicts (each a tile descriptor for
    `observed`, optionally carrying a `tile_path`).  Returns
    `(visioned_products, diagnostics)`:
      * visioned_products: the dicts `vision.call` produced (new/changed skus only)
      * diagnostics: {vision_calls, changed_skus, new_skus, skipped_skus, changed}
    When `vision` is None the path degrades to no vision calls (no crash).
    """
    prev = prev or []
    observed = observed or []
    # Dedup both snapshots by sku first (last-wins, first-seen order) so an
    # identical snapshot diffed against itself is empty — the precondition for the
    # "unchanged sku spends no vision call" guarantee, even when a tab repeats a
    # sku at two different prices (see `_dedup_by_sku`).
    prev_uniq = _dedup_by_sku(prev)
    obs_uniq = _dedup_by_sku(observed)
    prev_dc = [_to_dc_item(p) for _, p in prev_uniq]
    cur_dc = [_to_dc_item(o) for _, o in obs_uniq]
    # REUSE Tier A: changed/new skus == the skus that produce a change event.
    try:
        events = dc.detect_change(prev_dc, cur_dc, as_of=as_of)
        changed = {str(e["sku"]) for e in events}     # new_item + price_drop + ...
    except Exception:
        changed = set()
    prev_skus = {k for k, _ in prev_uniq if k is not None}

    visioned: list = []
    diag = {"vision_calls": 0, "changed_skus": [], "new_skus": [],
            "skipped_skus": [], "changed": []}
    for sk, o in obs_uniq:
        # an "unchanged" sku = present in prev AND produced no change event.
        unchanged = (sk is not None and sk in prev_skus and sk not in changed)
        if unchanged:
            diag["skipped_skus"].append(sk)
            continue                       # cost control: do NOT call vision
        if vision is None:                 # degrade, never crash
            continue
        tile_path = o.get("tile_path") if isinstance(o, dict) else None
        prod = vision.call(tile_path, schema)
        diag["vision_calls"] += 1
        # Normalize the vision output so an int sku becomes the canonical str sku —
        # type consistency across cost_control / assembly / alerts (one sku type).
        prod = normalize_mvm_product(prod)
        if prod is not None:
            visioned.append(prod)
        if sk is not None:
            if sk in prev_skus:
                diag["changed_skus"].append(sk)
            else:
                diag["new_skus"].append(sk)
            diag["changed"].append(sk)
    return visioned, diag


def build_mvm_catalog(prev_by_tab, observed_by_tab, manifest: dict = None,
                      vision=None, schema: Optional[dict] = None,
                      price_types: Optional[dict] = None,
                      as_of: Optional[str] = None):
    """End-to-end: for each MVM tab, cost-control vision over `observed_by_tab`
    tiles (only new/changed skus spend a vision call), merge the visioned
    products with the unchanged `prev` snapshot, and assemble the whole thing
    into the `p4.json` schema via `parse_and_assemble`.  Returns
    `(catalog, diagnostics)` where diagnostics aggregates the cost-control counts
    across every tab.  `prev_by_tab` / `observed_by_tab` are
    `{tab_id: [products]}`.  Both may be empty (fallback-safe)."""
    manifest = manifest or {}
    all_tab_ids: list = [str(t.get("tab_id")) for t in
                         (manifest.get("tabs") or []) if t.get("tab_id")]
    for tid in ((observed_by_tab or {}) or {}):
        if str(tid) not in all_tab_ids:
            all_tab_ids.append(str(tid))

    diagnostics = {"vision_calls": 0, "changed_skus": [], "new_skus": [],
                   "skipped_skus": [], "changed": []}
    flat: list = []
    for tid in all_tab_ids:
        prev = (prev_by_tab or {}).get(tid) or []
        observed = (observed_by_tab or {}).get(tid) or []
        visioned, diag = run_vision_with_cost_control(
            prev, observed, vision, schema=schema, as_of=as_of)
        diagnostics["vision_calls"] += diag["vision_calls"]
        diagnostics["changed_skus"] += diag["changed_skus"]
        diagnostics["new_skus"] += diag["new_skus"]
        diagnostics["skipped_skus"] += diag["skipped_skus"]
        diagnostics["changed"] += diag["changed"]
        # merge: unchanged prev snapshot is the base; visioned (new/changed) override
        by_sku: dict = {}
        for p in prev:
            k = _sku_of(p) or f"__noname_{id(p)}__"
            by_sku[k] = dict(p, tab_id=tid)
        for prod in visioned:
            pk = _sku_of(prod) or f"__noname_{id(prod)}__"
            base = dict(prod or {})
            base["tab_id"] = tid
            by_sku[pk] = base
        flat.extend(by_sku.values())

    catalog = parse_and_assemble(flat, manifest, price_types=price_types)
    return catalog, diagnostics


# --------------------------------------------------------------------------
# REAL vision provider — OUT OF CI (documented, never imported/constructed in tests)
# --------------------------------------------------------------------------
def build_real_vision_provider(provider_name: Optional[str] = None) -> VisionFn:
    """Construct the production vision model: Playwright screenshots + an LLM
    vision call, addressed via `MVM_VISION_PROVIDER` (e.g. `openai` / `anthropic`
    / `vertex`).  This is the **only** path that touches a real model or a
    browser; it is intentionally NOT exercised by the CI suite (offline,
    air-gapped).  Calling it WITHOUT the env var raises — so it can never
    silently run a half-configured real provider in CI.

    It performs LAZY imports of `playwright` / the LLM SDK *inside* the function,
    so that importing `mvm_vision` (which CI does) pulls in NEITHER.
    """
    name = (provider_name or os.environ.get("MVM_VISION_PROVIDER") or "").strip()
    if not name:
        raise RuntimeError(
            "MVM_VISION_PROVIDER 未設定；真實 vision 僅於 out-of-CI 路徑使用。"
            "（CI 不得觸發真實 vision / Playwright — 請注入 mock VisionFn。）"
        )
    # --- the below is out-of-CI; reached only when a provider is actually named ---
    try:
        from playwright.sync_api import sync_playwright        # noqa: F401 (out-of-CI)
    except Exception as exc:                                   # pragma: no cover
        raise RuntimeError(
            f"真實 vision 需要 Playwright（out-of-CI 路徑）：{type(exc).__name__}: {exc}"
        ) from exc
    # A real deployment would wire the named LLM SDK here.  We do not import it
    # at module load, and we never construct it in CI — so this stays a stub that
    # the out-of-CI runner completes.
    raise RuntimeError(
        f"真實 vision provider '{name}' 為 out-of-CI 路徑：於 CI 中注入 mock VisionFn，"
        "勿觸發真實 Playwright/LLM。"
    )
