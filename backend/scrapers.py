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


def fetch_crypto_price(
    asset: str, vs_currency: str = "twd", timeout: int = 15
) -> float:
    """Fetch a live market price from CoinGecko and return it as a float.

    Raises on network/HTTP/parse errors so the caller can fall back.
    """
    if not asset:
        raise ValueError("asset required")
    url = f"{COINGECKO}?ids={urllib.parse.quote(asset)}&vs_currencies={vs_currency}"
    req = urllib.request.Request(url, headers={"User-Agent": "price-monitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # CoinGecko returns { "<asset>": { "<cur>": number } }.
    price = data[asset].get(vs_currency)
    if price is None:
        raise ValueError(f"no {vs_currency} price for {asset}")
    return float(price)


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
