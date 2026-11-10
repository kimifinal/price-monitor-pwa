"""Offline tests for the Costco *basket* scraper (costco.py) — no network.

parse_products runs against a representative fixture whose tile markup mirrors
the real Costco.com.tw structure. The fetch failure path is mocked. This keeps
CI green with no live dependency while proving the multi-tile extraction logic.
"""
import os

import costco as _costco_module
from costco import (
    parse_products,
    filter_basket,
    pdp_name,
    related_appliance_urls,
    crawl_appliances,
    _parse_price,
    _tag_for,
    fetch,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "costco_3c_basket.html")
PDP_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "pdp_appliance.html")


def _fixture_html() -> str:
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def test_parse_products_reads_all_five_tiles():
    products = parse_products(_fixture_html())
    assert len(products) == 5
    for p in products:
        assert p["name"] and p["currency"] == "TWD" and p["sku"] and p["tag"]


def test_prices_parsed_with_commas_and_currency_symbol():
    by_sku = {p["sku"]: p["price"] for p in parse_products(_fixture_html())}
    assert by_sku["157304"] == 53999.0  # Apple iPad Pro
    assert by_sku["149699"] == 1369.0   # ANKER charger
    assert by_sku["3062725"] == 8149.0  # BOSE Soundbar
    assert by_sku["239289"] == 929.0    # paper towel
    assert by_sku["157689"] == 1299.0   # mouse pad (name via img[alt] fallback)


def test_name_falls_back_to_image_alt():
    by_sku = {p["sku"]: p for p in parse_products(_fixture_html())}
    assert "滑鼠墊" in by_sku["157689"]["name"]


def test_tag_detection_from_url_breadcrumb():
    by_sku = {p["sku"]: p["tag"] for p in parse_products(_fixture_html())}
    assert by_sku["157304"] == "3C"
    assert by_sku["3062725"] == "家電"
    assert by_sku["239289"] == "其他"


def test_filter_basket_keeps_only_3c_and_appliance():
    kept = filter_basket(parse_products(_fixture_html()))
    assert {p["tag"] for p in kept} <= {"3C", "家電"}
    assert len(kept) == 4  # the 其他 paper-towel tile is dropped


def test_parse_price_helper():
    assert _parse_price("NT$53,999.00") == 53999.0
    assert _parse_price(" $1,234 ") == 1234.0
    assert _parse_price("") is None


def test_tag_for_helpers():
    assert _tag_for("/Televisions-Appliances/Kitchen-Appliances/x/p/1") == "家電"
    assert _tag_for("/Digital-Mobile/Peripherals/x/p/1") == "3C"
    assert _tag_for("/Household-Baby-Toys/Food/x/p/1") == "其他"


def test_parse_products_empty_html_returns_empty_list():
    assert parse_products("") == []
    assert parse_products("<html>no tiles here</html>") == []


def test_fetch_returns_none_on_network_failure():
    import urllib.error
    import urllib.request

    orig = _costco_module.urllib.request.urlopen

    def boom(*a, **k):
        raise urllib.error.URLError("no network")

    try:
        _costco_module.urllib.request.urlopen = boom
        assert fetch("https://www.costco.com.tw/c/1") is None
    finally:
        _costco_module.urllib.request.urlopen = orig


# ----------------------- 家電 BFS crawl 測試（離線）----------------------------
def _pdp_html() -> str:
    with open(PDP_FIXTURE, encoding="utf-8") as f:
        return f.read()


def test_related_appliance_urls_returns_only_家电():
    urls = related_appliance_urls(_pdp_html())
    # 3 連結：Samsung、Klipsch 是 家電（Televisions-Appliances/），HP 筆電是 3C（Digital-Mobile/）
    assert any("Samsung-55" in u for u in urls)
    assert any("Klipsch-Flexus" in u for u in urls)
    assert not any("HP-EliteBook" in u for u in urls)  # 3C 被過濾掉
    for u in urls:
        assert _tag_for(u) == "家電"


def test_pdp_name_strips_costco_suffix():
    assert "飛利浦 55吋 4K Google TV 智慧顯示器" in (pdp_name(_pdp_html()) or "")


def test_crawl_appliances_grows_basket_via_mocked_fetch(monkeypatch):
    import scrapers  # crawl lazy-imports scrape_costco from here
    html = _pdp_html()

    def fake_fetch(url, timeout=20):
        return html if "153526" in url else None

    def fake_scrape(url, timeout=20):
        return {
            "price": 12599.0,
            "currency": "TWD",
            "sku": "153526",
        } if "153526" in url else None

    # fetch 決定 2nd URL 是否加入；scrape_costco 決定 1st URL 是否入籃
    monkeypatch.setattr(_costco_module, "fetch", fake_fetch)
    monkeypatch.setattr(scrapers, "scrape_costco", fake_scrape)

    basket = crawl_appliances(
        [f"{_costco_module.BASE}/x/y/Philips/p/153526"],
        max_items=5,
        max_requests=10,
        delay=0,
    )
    assert len(basket) == 1  # A 入籃，B（fetch 回 None）沒進來
    assert basket[0]["sku"] == "153526"
    assert basket[0]["name"] == "飛利浦 55吋 4K Google TV 智慧顯示器"
    assert basket[0]["tag"] == "家電"
    assert basket[0]["price"] == 12599.0
