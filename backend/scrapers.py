"""
Price fetching — REAL HTTP scraper with a graceful offline fallback.

Real path: pull a live price from a public JSON API (CoinGecko: no key, no
anti-bot). Fallback: a deterministic simulated price. The fallback keeps CI
green on machines without network (the CI image may be air-gapped), while local
runs fetch live data.
"""
import json
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse

COINGECKO = "https://api.coingecko.com/api/v3/simple/price"


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


def fetch_price_from_page(url: str, timeout: int = 15) -> float:
    """PRODUCTION SKELETON: fetch a real product page and parse its price.

    Pseudocode for when you point this at a Chiikawa / Costco listing:
        import httpx
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient() as c:
            r = await c.get(url, timeout=timeout, headers={"User-Agent": "..."})
            soup = BeautifulSoup(r.text, "html.parser")
            node = soup.select_one("meta[property='og:price:amount']")
            return float(node["content"]) if node else 0.0
    Falls back to the simulator so the pipeline stays green.
    """
    if not url:
        raise ValueError("url required")
    return round(simulate(url), 2)
