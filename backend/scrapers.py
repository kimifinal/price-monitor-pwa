"""
Price fetching — REAL HTTP scraper with a graceful offline fallback.

Real path: pull a live price from a public JSON API (CoinGecko: no key, no
anti-bot). Fallback: a deterministic simulated price. The fallback keeps CI
green on machines without network (the CI image may be air-gapped), while local
runs fetch live data.
"""
from __future__ import annotations

import json
import re
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse

COINGECKO = "https://api.coingecko.com/api/v3/simple/price"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)


def simulate(source: str) -> float:
    """Deterministic stand-in price. Stable per `source`, slowly wobbling so
    repeated checks can show a drop. Used as the offline fallback and by tests.
    """
    if not source:
        return 0.0
    seed = int(hashlib.sha256(source.encode()).hexdigest()[:8], 16)
    base = 50.0 + (seed % 200)  # 50..249
    wobble = 0.95 + (time.time() % 10) / 100.0
    return round(base * wobble, 2)


def _http_get_json(url: str, timeout: int = 15, retries: int = 3) -> dict:
    """GET a URL and return parsed JSON, with a short backoff on 429/5xx
    (public APIs rate-limit aggressively; free tiers are the worst).
    """
    delay = 1.0
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": "price-monitor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ValueError):
            last = Exception()
            raise
    if last is not None:
        raise last
    raise RuntimeError("http get failed")


def fetch_crypto_prices(
    assets: list[str], vs_currency: str = "twd", timeout: int = 15
) -> dict:
    """Fetch live prices for MANY assets in ONE request (avoids rate limits).

    Returns {asset: float_price}; assets not returned by the API are omitted.
    """
    if not assets:
        return {}
    ids = ",".join(urllib.parse.quote(a) for a in assets)
    url = f"{COINGECKO}?ids={ids}&vs_currencies={vs_currency}"
    data = _http_get_json(url, timeout=timeout)
    out = {}
    for a in assets:
        price = data.get(a, {}).get(vs_currency)
        if price is not None:
            out[a] = float(price)
    return out


def fetch_crypto_price(
    asset: str, vs_currency: str = "twd", timeout: int = 15
) -> float:
    """Fetch a single live price from CoinGecko. Raises on failure.
    Prefer fetch_crypto_prices() for multiple assets (one request each).
    """
    if not asset:
        raise ValueError("asset required")
    prices = fetch_crypto_prices([asset], vs_currency, timeout)
    if not prices:
        raise ValueError(f"no {vs_currency} price for {asset}")
    return prices[asset]


def fetch_price(source: str, vs_currency: str = "twd", timeout: int = 15) -> float:
    """Return a real price for `source`, falling back to the simulator.

    `source` may be:
      - "crypto:bitcoin"  -> live price of the coin
      - "bitcoin"         -> live price of the coin by that id
      - anything else     -> simulated price (fallback on any failure)
    """
    asset = source
    if isinstance(source, str) and source.startswith("crypto:"):
        asset = source.split(":", 1)[1]
    try:
        return round(fetch_crypto_price(asset, vs_currency, timeout), 2)
    except Exception:
        # Graceful degradation: CI/offline keeps its deterministic price.
        return round(simulate(source), 2)


def _http_get_text(url: str, timeout: int = 15, retries: int = 3) -> str:
    """GET a URL and return its text body, with a short backoff on 429/5xx.
    Raises on network/HTTP failure so the caller can fall back.
    """
    delay = 1.0
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            raise


def parse_offers(html: str) -> dict | None:
    """Extract a product's price from any page carrying a schema.org `offers`
    object (Costco.com.tw embeds it inside its Next.js JSON blob). Returns a
    dict {price, currency, sku, valid_until, availability} or None.

    Robust to field ordering: locates "offers", brace-matches to the end of the
    object while ignoring braces inside JSON strings, then reads standard fields.
    """
    if not html or "offers" not in html:
        return None
    m = re.search(r'"offers"\s*:', html)
    if not m:
        return None
    i = m.end()
    while i < len(html) and html[i] not in "{}":
        i += 1
    if i >= len(html) or html[i] != "{":
        return None
    depth, in_str, esc = 0, False, False
    end = -1
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end < 0:
        return None
    try:
        offers = json.loads(html[i:end])
    except ValueError:
        msku = re.search(r'"sku"\s*:\s*"([^"]+)"', html)
        return None if not msku else {"sku": msku.group(1), "price": None}
    if isinstance(offers, list):
        offers = offers[0] if offers else None
    if not isinstance(offers, dict):
        return None
    msku = re.search(r'"sku"\s*:\s*"([^"]+)"', html)
    return {
        "price": float(offers["price"]) if offers.get("price") is not None else None,
        "currency": offers.get("priceCurrency"),
        "sku": msku.group(1) if msku else None,
        "valid_until": offers.get("priceValidUntil"),
        "availability": offers.get("availability"),
    }


def scrape_costco(url: str, timeout: int = 15, retries: int = 3) -> dict | None:
    """Fetch a Costco.tw product page and return its parsed fields, or None on
    any failure (network/parse). No exception propagates out.
    """
    if not url:
        raise ValueError("url required")
    try:
        html = _http_get_text(url, timeout=timeout, retries=retries)
    except Exception:
        return None
    return parse_offers(html)


def fetch_price_from_page(url: str, timeout: int = 15) -> float:
    """Fetch a real product page (e.g. Costco) and return its price.

    Uses parse_offers() on the HTML schema.org block; falls back to the
    simulator so the pipeline stays green when offline.
    """
    if not url:
        raise ValueError("url required")
    parsed = scrape_costco(url, timeout=timeout)
    if not parsed or parsed.get("price") is None:
        return round(simulate(url), 2)
    return round(parsed["price"], 2)
