"""B2 (Tier B of #35) — offline tests for MVM vision 抽價 + cost control.

AC coverage (mvm_vision), ALL offline:
  * ASSEMBLY   — mock VisionFn + 合成 tile -> `parse_and_assemble` builds a dict
                 that matches the `p4.json` schema (`{tabs:[{...products[]}],
                 price_types:{3}}`), in manifest tab order, per-tab `n_products`.
  * COST CTRL  — an UNCHANGED sku (present in `prev`, identical) does NOT spend a
                 vision call; only NEW / CHANGED skus do (spy asserts the count).
                 The change/new test REUSES Tier A `detect_change`.
  * OUT-OF-CI  — the real vision provider (`MVM_VISION_PROVIDER` + Playwright +
                 LLM) is never imported/constructed here; CI stays air-gapped.
"""
import json
import struct
from pathlib import Path

import mvm_vision as M
import mvm_detect
from mvm_vision import VisionFn

P4_PATH = Path(__file__).resolve().parents[2] / "data" / "costco_mvm" / "2026-11-16_mvm_p4.json"
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "costco_mvm" / "manifest.json"

P4 = json.loads(P4_PATH.read_text(encoding="utf-8"))
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

# canonical 7-field product shape (p4.json SSOT)
REQUIRED_FIELDS = ("sku", "name", "orig", "promo", "discount", "type", "cat")


class SpyVision:
    """A vision spy: records every `call(tile_path, schema)` and returns a
    pre-canned product (or one derived from the `tile_path`). It is what makes the
    'unchanged sku never calls vision' AC observable via `call_count`.

    It satisfies the runtime_checkable `VisionFn` protocol, proving the contract."""

    def __init__(self, products_by_tile=None, default=None):
        self.calls = []                       # list of (tile_path, schema)
        self._by_tile = products_by_tile or {}
        self._default = default

    def call(self, tile_path, schema=None):
        self.calls.append((tile_path, schema))
        if tile_path in self._by_tile:
            return self._by_tile[tile_path]
        if self._default is not None:
            return self._default() if callable(self._default) else dict(self._default)
        # a sensible synthetic product so assembly has something to place
        return {"sku": str(hash(tile_path))[:6], "name": f"p{tile_path}",
                "orig": 1000, "promo": 800, "discount": 200,
                "type": "online_only", "cat": "測試"}

    @property
    def call_count(self) -> int:
        """How many vision calls happened — the knob the cost-control AC asserts."""
        return len(self.calls)


# --------------------------- VisionFn protocol conformance ---------------------------

def test_visionfn_is_a_runtime_checkable_protocol():
    assert getattr(VisionFn, "_is_runtime_protocol", False) is True
    assert isinstance(SpyVision(), VisionFn)          # spy conforms to the protocol
    # the schema constant the caller hands vision is the 7-field shape
    assert set(M.SCHEMA.keys()) == set(REQUIRED_FIELDS)


def test_spy_records_the_contract_arguments():
    spy = SpyVision()
    prod = spy.call("tile.png", M.SCHEMA)
    assert len(spy.calls) == 1
    tile_path, schema = spy.calls[0]
    assert tile_path == "tile.png" and schema == M.SCHEMA
    assert set(prod.keys()) == set(REQUIRED_FIELDS)    # returns the full shape


# --------------------------- tile coordinate math (offline) ---------------------------

def test_tile_coords_pure_math():
    assert M.tile_coords(600, 600) == [(0, 0, 600)]                       # exact tile
    assert M.tile_coords(601, 600) == [(0, 0, 600), (1, 600, 601)]       # +1px -> 2 tiles
    assert M.tile_coords(1500, 600) == [(0, 0, 600), (1, 600, 1200), (2, 1200, 1500)]
    assert M.tile_coords(1201, 600) == [(0, 0, 600), (1, 600, 1200), (2, 1200, 1201)]
    assert M.tile_coords(0, 600) == []                                   # degenerate
    assert M.tile_coords(1500, 0) == []                              # bad tile size
    assert M.tile_coords(None, 600) == [] and M.tile_coords(1500, None) == []


def test_tile_screenshot_is_offline_and_names_siblings(tmp_path):
    paths = M.tile_screenshot("/nonexistent/img.png", tile_h=600, height=1800,
                              out_dir=str(tmp_path))
    assert len(paths) == 3
    assert [p.split("/")[-1] for p in paths] == [
        "img__tile_000.png", "img__tile_001.png", "img__tile_002.png"]
    assert str(tmp_path) in paths[0]
    # an injectable opener overrides the default reader
    paths2 = M.tile_screenshot("anything", tile_h=600,
                               opener=lambda p: 1500, out_dir=str(tmp_path))
    assert len(paths2) == 3


def test_tile_screenshot_default_requires_height_or_opener(tmp_path):
    # CI never decodes pixels: no height + no opener => a clear error, not a crash
    import pytest
    with pytest.raises(ValueError):
        M.tile_screenshot(str(tmp_path / "nope.png"), tile_h=600)


def test_read_png_height_stdlib_only(tmp_path):
    # a real, hand-built PNG (stdlib struct) proves the offline reader has no 3rd dep
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 800, 2400) + b"\x08\x02" + b"\x00\x00\x00\x00"
    png = tmp_path / "mvm.png"
    png.write_bytes(sig + ihdr)
    assert M._read_png_height(str(png)) == 2400
    assert len(M.tile_screenshot(str(png), tile_h=600)) == 4       # 2400/600 -> 4 tiles
    # a non-PNG degrades to a clear error (no crash)
    import pytest
    bad = tmp_path / "not.png"
    bad.write_bytes(b"hello")
    with pytest.raises(ValueError):
        M._read_png_height(str(bad))


# --------------------------- product normalization ---------------------------

def test_normalize_mvm_product_keeps_type_variants_and_coerces():
    # the real data has finer subtypes: keep them, coerce numeric strings, map null
    p = M.normalize_mvm_product({
        "sku": 149471, "name": "TCL 洗衣機", "orig": "9999", "promo": "7999",
        "discount": "2000", "type": "online_only", "cat": "家電"})
    assert p["sku"] == "149471"                      # sku stringified for dedup
    assert p["orig"] == 9999 and p["promo"] == 7999 and p["discount"] == 2000
    assert p["type"] == "online_only" and p["cat"] == "家電"
    assert set(p.keys()) == set(REQUIRED_FIELDS)
    # a store-only *subtype* is preserved, never collapsed
    p2 = M.normalize_mvm_product({"sku": 5, "name": "x", "orig": 1, "promo": 1,
                                  "discount": 0, "type": "store_only_special", "cat": "食品"})
    assert p2["type"] == "store_only_special"
    # junk -> None, and a null / empty type maps to None
    assert M.normalize_mvm_product({"type": "null", "name": ""}) is None
    assert M.normalize_mvm_product({}) is None
    p3 = M.normalize_mvm_product({"sku": 9, "name": "y", "type": "   "})
    assert p3["type"] is None


# --------------------------- p4.json-style assembly ---------------------------

def test_parse_and_assemble_matches_p4_schema_in_manifest_order():
    # one tab filled, others empty; new ids absent from manifest are synthesized
    products = [
        {"tab_id": "fy27p3-mvm2-w1", "sku": 100, "name": "A", "orig": 1000,
         "promo": 900, "discount": 100, "type": "online_only", "cat": "家清"},
        {"tab_id": "fy27p3-mvm2-w1", "sku": 200, "name": "B", "orig": 1200,
         "promo": 950, "discount": 250, "type": "store_online_diff", "cat": "食品"},
        {"tab_id": "fy27p4-mvm2-weekday", "sku": 300, "name": "C", "orig": 500,
         "promo": 400, "discount": 100, "type": "store_only", "cat": "個護"},
    ]
    cat = M.parse_and_assemble(products, MANIFEST, price_types=P4["price_types"])
    # top-level shape exactly matches p4.json
    assert set(cat.keys()) == {"tabs", "price_types"}
    assert set(cat["price_types"].keys()) == set(P4["price_types"].keys())
    # 6 manifest tabs, in manifest order, each with n_products == len(products)
    tab_ids = [t["tab_id"] for t in cat["tabs"]]
    assert tab_ids == [t["tab_id"] for t in MANIFEST["tabs"]]
    for t in cat["tabs"]:
        assert t["n_products"] == len(t["products"])
        for p in t["products"]:
            assert "tab_id" not in p                  # tab_id is stripped from the product
            assert set(p.keys()) == set(REQUIRED_FIELDS)
    by_id = {t["tab_id"]: t for t in cat["tabs"]}
    assert len(by_id["fy27p3-mvm2-w1"]["products"]) == 2
    assert len(by_id["fy27p4-mvm2-weekday"]["products"]) == 1
    # an empty manifest tab is still emitted (schema-faithful: p4 has 0-product tabs)
    assert by_id["fy27p4-mvm2-cyber"]["products"] == []
    # metadata (label/period/url/price_type/description) carried from the manifest
    assert by_id["fy27p3-mvm2-w1"]["price_type"] == "online_online_diff"
    assert by_id["fy27p3-mvm2-w1"]["url"].endswith("/fy27p3-mvm2-w1")


def test_parse_and_assemble_dedups_by_sku_last_wins():
    products = [
        {"tab_id": "fy27p3-mvm2-w1", "sku": 100, "name": "OLD", "orig": 1000,
         "promo": 700, "discount": 300, "type": "online_only", "cat": "x"},
        {"tab_id": "fy27p3-mvm2-w1", "sku": 100, "name": "NEW", "orig": 1000,
         "promo": 600, "discount": 400, "type": "online_only", "cat": "x"},
    ]
    cat = M.parse_and_assemble(products, MANIFEST)
    w1 = next(t for t in cat["tabs"] if t["tab_id"] == "fy27p3-mvm2-w1")
    assert len(w1["products"]) == 1                      # deduped
    assert w1["products"][0]["name"] == "NEW"            # last write wins
    assert w1["products"][0]["promo"] == 600


def test_parse_and_assemble_accepts_per_tab_batches_and_unknown_tab():
    # a per-tab *batch* record, plus a brand-new tab not in the manifest
    tiles = [
        {"tab_id": "fy27p3-mvm2-w1", "products": [
            {"sku": 1, "name": "A", "orig": 10, "promo": 8, "type": "online_only", "cat": "c"},
            {"sku": 2, "name": "B", "orig": 20, "promo": 10, "type": "online_only", "cat": "c"}]},
        {"tab_id": "fy27p5-mvm2-w1", "sku": 99, "name": "Z", "orig": 5, "promo": 4,
         "type": "online_only", "cat": "c", "tile_path": "z.png"},
    ]
    cat = M.parse_and_assemble(tiles, MANIFEST)
    ids = {t["tab_id"] for t in cat["tabs"]}
    assert "fy27p5-mvm2-w1" in ids                 # the new tab is added
    new_tab = next(t for t in cat["tabs"] if t["tab_id"] == "fy27p5-mvm2-w1")
    assert new_tab["url"].endswith("/fy27p5-mvm2-w1")   # synthesized metadata
    assert len(next(t for t in cat["tabs"] if t["tab_id"] == "fy27p3-mvm2-w1")["products"]) == 2
    # missing price_types falls back to the canonical 3
    cat2 = M.parse_and_assemble([], MANIFEST)
    assert set(cat2["price_types"].keys()) == {"online_only", "store_online_diff", "store_only"}


# --------------------------- cost control: unchanged never calls vision ---------------------------
#
# THE CORE AC: an unchanged sku spends NO vision call; only new / changed do.
# The new/changed decision REUSES Tier A detect_change (its events == changed/new).

def _w1_products():
    for t in P4["tabs"]:
        if t["tab_id"] == "fy27p3-mvm2-w1":
            return [dict(p, tab_id="fy27p3-mvm2-w1") for p in t.get("products", [])]
    raise AssertionError("w1 tab not found")


def test_identical_snapshot_never_calls_vision_real_data(tmp_path):
    prods = _w1_products()
    assert len(prods) > 0                                   # the real w1 tab
    spy = SpyVision()
    # observed == prev, verbatim -> every sku is unchanged -> zero vision calls
    visioned, diag = M.run_vision_with_cost_control(prods, prods, spy,
                                                    schema=M.SCHEMA, as_of="2026-11-18")
    assert spy.calls == []                                  # <-- the cost-control guarantee
    assert diag["vision_calls"] == 0
    assert len(diag["skipped_skus"]) == len({p["sku"] for p in prods})
    assert visioned == []


def test_changed_and_new_skus_are_the_only_ones_visioned():
    # prev: two skus at a stable price; observed: one identical, one dropped, one new
    prev = [
        {"sku": 100, "name": "keep", "orig": 1000, "promo": 800, "type": "online_only", "cat": "c"},
        {"sku": 200, "name": "drop", "orig": 1200, "promo": 1000, "type": "online_only", "cat": "c"},
    ]
    obs = [
        {"sku": 100, "name": "keep", "orig": 1000, "promo": 800, "tile_path": "t100"},
        {"sku": 200, "name": "drop", "orig": 1200, "promo": 900, "tile_path": "t200"},  # promo 1000->900
        {"sku": 300, "name": "new", "orig": 500, "promo": 400, "tile_path": "t300",
         "type": "online_only", "cat": "3C"},                                                # brand new
    ]
    by_tile = {"t200": {"sku": 200, "name": "drop", "orig": 1200, "promo": 900,
                        "discount": 300, "type": "online_only", "cat": "c"},
               "t300": {"sku": 300, "name": "new", "orig": 500, "promo": 400,
                        "discount": 100, "type": "online_only", "cat": "3C"}}
    spy = SpyVision(products_by_tile=by_tile)
    visioned, diag = M.run_vision_with_cost_control(prev, obs, spy,
                                                    schema=M.SCHEMA, as_of="2026-11-18")
    # EXACTLY the changed/new skus — the unchanged sku 100 never touched vision
    assert [tp for tp, _ in spy.calls] == ["t200", "t300"]
    assert 100 not in {tp for tp, _ in spy.calls}
    assert diag["vision_calls"] == 2
    assert "100" in diag["skipped_skus"]
    assert "200" in diag["changed_skus"]
    assert "300" in diag["new_skus"]
    assert {p["sku"] for p in visioned} == {"200", "300"}


def test_first_run_prev_empty_visits_everything():
    obs = [{"sku": 1, "name": "a", "orig": 10, "promo": 8, "tile_path": "t1"},
           {"sku": 2, "name": "b", "orig": 20, "promo": 15, "tile_path": "t2"}]
    spy = SpyVision()
    visioned, diag = M.run_vision_with_cost_control([], obs, spy)
    assert spy.calls and len(spy.calls) == 2          # a fresh catalog visions every sku
    assert len(visioned) == 2
    assert set(diag["new_skus"]) == {"1", "2"}
    assert diag["skipped_skus"] == []


def test_vision_none_degrades_without_crash():
    visioned, diag = M.run_vision_with_cost_control([],
        [{"sku": 1, "name": "a", "orig": 10, "promo": 8, "tile_path": "t1"}],
        vision=None)
    assert visioned == [] and diag["vision_calls"] == 0


# --------------------------- end-to-end build + schema ---------------------------

def test_build_mvm_catalog_assembles_valid_schema_and_cost_controls(tmp_path):
    prev_by_tab = {"fy27p3-mvm2-w1": [
        {"sku": 100, "name": "keep", "orig": 1000, "promo": 800, "type": "online_only", "cat": "c"},
        {"sku": 200, "name": "drop", "orig": 1200, "promo": 1000, "type": "online_only", "cat": "c"}]}
    obs_by_tab = {"fy27p3-mvm2-w1": [
        {"sku": 100, "name": "keep", "orig": 1000, "promo": 800, "tile_path": "t100"},
        {"sku": 200, "name": "drop", "orig": 1200, "promo": 900, "tile_path": "t200"}]}
    by_tile = {"t200": {"sku": 200, "name": "drop", "orig": 1200, "promo": 900,
                        "discount": 300, "type": "online_only", "cat": "c"}}
    spy = SpyVision(products_by_tile=by_tile)
    catalog, diag = M.build_mvm_catalog(prev_by_tab, obs_by_tab, MANIFEST,
                                        vision=spy, price_types=P4["price_types"],
                                        as_of="2026-11-18")
    # schema-valid
    assert set(catalog.keys()) == {"tabs", "price_types"}
    for t in catalog["tabs"]:
        assert t["n_products"] == len(t["products"])
        assert all(set(p.keys()) == set(REQUIRED_FIELDS) for p in t["products"])
    w1 = next(t for t in catalog["tabs"] if t["tab_id"] == "fy27p3-mvm2-w1")
    skus = sorted(p["sku"] for p in w1["products"])
    assert skus == ["100", "200"]                       # unchanged merged + changed visioned
    assert [p for p in w1["products"] if p["sku"] == "100"][0]["name"] == "keep"
    assert [p for p in w1["products"] if p["sku"] == "200"][0]["promo"] == 900  # visioned new val
    # cost control: only sku 200 (changed) was visioned; 100 was merged unchanged
    assert diag["vision_calls"] == 1
    assert "100" in diag["skipped_skus"]
    assert "200" in diag["changed_skus"]


# --------------------------- the real provider is OUT OF CI ---------------------------

def test_build_real_vision_provider_refuses_without_env(monkeypatch):
    import sys
    monkeypatch.delenv("MVM_VISION_PROVIDER", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        M.build_real_vision_provider()
    # importing mvm_vision (which CI does) never pulls Playwright into sys.modules
    assert "playwright" not in sys.modules
    assert "playwright.sync_api" not in sys.modules


def test_real_provider_needs_a_named_provider(monkeypatch):
    monkeypatch.setenv("MVM_VISION_PROVIDER", "openai")
    import pytest
    with pytest.raises(RuntimeError):                   # out-of-CI: never constructs for real
        M.build_real_vision_provider("openai")
