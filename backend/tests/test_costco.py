"""Tests for the real Costco HTML scraper — offline, deterministic.

The parser runs against a captured fixture (no network). The fetch layer's
failure path is mocked. This keeps CI green with no live dependency while
proving the real extraction logic.
"""
import os
from unittest.mock import patch

from scrapers import (
    parse_offers,
    scrape_costco,
    fetch_price_from_page,
    _http_get_text,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "costco_30991.html")


def _fixture() -> str:
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def test_parse_offers_reads_real_costco_price():
    r = parse_offers(_fixture())
    assert r is not None
    assert r["price"] == 459.0
    assert r["currency"] == "TWD"
    assert r["sku"] == "30991"
    assert r["availability"] == "http://schema.org/InStock"
    assert r["valid_until"] == "2026-11-16"


def test_parse_offers_missing_offers_returns_none():
    assert parse_offers("<html>no structured data</html>") is None
    assert parse_offers("") is None


def test_parse_offers_handles_list_of_offers():
    html = 'x {"offers":[{"price":"10.5","priceCurrency":"USD"}]}'
    r = parse_offers(html)
    assert r["price"] == 10.5
    assert r["currency"] == "USD"


def test_parse_offers_missing_price_field():
    html = 'x {"offers":{"priceCurrency":"TWD","price":null}}"sku":"99"'
    r = parse_offers(html)
    assert r["price"] is None


def test_scrape_costco_network_failure_returns_none():
    with patch(
        "scrapers._http_get_text", side_effect=OSError("network down")
    ):
        assert scrape_costco("https://www.costco.com.tw/p/30991") is None


def test_scrape_costco_parses_fixture_over_mocked_network():
    with patch("scrapers._http_get_text", return_value=_fixture()):
        r = scrape_costco("https://www.costco.com.tw/p/30991")
        assert r["price"] == 459.0


def test_fetch_price_from_page_falls_back_on_failure():
    with patch(
        "scrapers._http_get_text", side_effect=OSError("network down")
    ):
        # Must not raise; returns a deterministic simulated price > 0.
        p = fetch_price_from_page("https://www.costco.com.tw/p/30991")
        assert isinstance(p, float) and p > 0


def test_fetch_price_from_page_empty_url():
    try:
        fetch_price_from_page("")
        assert False
    except ValueError:
        pass
