"""Tests for the real scraper + its offline fallback."""
import json
from unittest.mock import patch, MagicMock
from scrapers import fetch_crypto_price, fetch_price, simulate, fetch_price_from_page


def _fake_response(payload: dict):
    """Build a context-manager-able fake urllib response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


def test_fetch_crypto_price_parses_live_payload():
    with patch(
        "scrapers.urllib.request.urlopen",
        return_value=_fake_response({"bitcoin": {"twd": 2453399}}),
    ):
        price = fetch_crypto_price("bitcoin", "twd")
        assert price == 2453399.0


def test_fetch_password_missing_currency_raises():
    with patch(
        "scrapers.urllib.request.urlopen",
        return_value=_fake_response({"bitcoin": {"usd": 100}}),
    ):
        try:
            fetch_crypto_price("bitcoin", "twd")
            assert False, "expected ValueError when currency missing"
        except ValueError:
            pass


def test_fetch_price_dispatches_crypto_prefix_and_falls_back():
    # Network failure -> must fall back to the simulator (deterministic).
    with patch(
        "scrapers.urllib.request.urlopen",
        side_effect=OSError("network down"),
    ):
        p1 = fetch_price("crypto:bitcoin", "twd", timeout=1)
        p2 = fetch_price("crypto:bitcoin", "twd", timeout=1)
        assert p1 == p2  # deterministic fallback
        assert p1 > 0


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
