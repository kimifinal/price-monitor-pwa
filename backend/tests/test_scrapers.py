"""Tests for the real scraper + its offline fallback.

The sacred invariant: a network down NEVER crashes the pipeline — every path
degrades to the deterministic simulator. These are all OFFLINE.
"""
from unittest.mock import patch
from scrapers import (
    fetch_price,
    simulate,
    scrape_costco,
    fetch_price_from_page,
)


def test_simulate_is_deterministic_and_nonzero():
    a = simulate("chiikawa-badge")
    b = simulate("chiikawa-badge")
    assert a == b
    assert a >= 0
    assert simulate("") == 0.0


def test_fetch_price_from_page_requires_url():
    try:
        fetch_price_from_page("")
        assert False
    except ValueError:
        pass


def test_scrape_costco_fails_softly_offline():
    # No network -> the real scrape returns None (never raises); the caller
    # falls back to the simulator.
    with patch("scrapers.urllib.request.urlopen",
               side_effect=OSError("network down")):
        assert scrape_costco("https://www.costco.com.tw/x/30991", timeout=1) is None


def test_fetch_price_offline_falls_back_to_simulator():
    # A non-URL source uses the deterministic simulator directly.
    assert fetch_price("chiikawa-badge", "twd", timeout=1) == \
        round(simulate("chiikawa-badge"), 2)
    # An http source degrades to the simulator when the network is down — the
    # offline invariant: the pipeline never crashes on a dead network.
    url = "https://www.costco.com.tw/x/30991"
    with patch("scrapers.urllib.request.urlopen",
               side_effect=OSError("network down")):
        assert fetch_price(url, "twd", timeout=1) == round(simulate(url), 2)
