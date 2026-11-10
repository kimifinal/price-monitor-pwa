"""
Price fetching — SCAFFOLD.

`fetch_price` returns a *simulated* price derived from the item so the whole
pipeline runs with no external dependency. In production, replace the body with
an HTTP fetch + HTML/JSON parse of the real product page (e.g. via `httpx`).
"""
import hashlib
import time


def fetch_price(source: str) -> float:
    """Return a deterministic-but-varying simulated price for `source`.

    Deterministic so tests are stable; varies over time so repeated checks can
    show a "drop". Not real scraping — a stand-in for the parser.
    """
    if not source:
        return 0.0
    # Stable hash -> base, plus a slow time-based wobble in [0.9, 1.1].
    seed = int(hashlib.sha256(source.encode()).hexdigest()[:8], 16)
    base = 50.0 + (seed % 200)  # 50..249
    wobble = 0.95 + (time.time() % 10) / 100.0
    return round(base * wobble, 2)


def fetch_price_from_page(url: str) -> float:
    """PRODUCTION SKELLET: fetch a real product page and parse its price.

    Pseudocode for when you make this real — left as a documented stub so the
    pipeline (lint/coverage/e2e) has a real branch to exercise:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            m = soup.select_one("meta[property='og:price:amount']")
            return float(m["content"]) if m else 0.0
    """
    if not url:
        raise ValueError("url required")
    # Real implementation would go here. Return the simulated price for now.
    return fetch_price(url)
