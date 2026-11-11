"""crypto.py — connect crypto (CoinGecko) into the 時序比價 layer (#3).

The time-series layer (`history.py`) is *source-agnostic*: an observation just
carries a `source` column. CoinGecko is one more source beside `costco`. This
module is crypto's entry into that shared layer. It:

  * does ONE bulk CoinGecko request for every watchlist coin, with a
    deterministic offline fallback (`scrapers.simulate`) that NEVER raises — so a
    no-network run returns a fallback price instead of crashing; and
  * tags every point `source="coingecko"` so crypto coexists in the SAME
    `history_data.json` / time-series + verdict layer as Costco (multi-source).

Offline-safe invariant (sacred): a fallback point is marked `synthetic=1`. The
alert scanner fires ONLY on `current_is_real` (see alerts.py), so a fallback
(synthetic) point can never produce a false "buy now" — exactly what keeps an
offline / fallback pipeline from shouting.
"""
from __future__ import annotations

import history
from scrapers import fetch_crypto_prices, simulate

SOURCE = "coingecko"        # the label crypto points carry (beside 'costco')
DEFAULT_VS = "twd"
DEFAULT_TIMEOUT = 15

# A small, stable watchlist. sku = "crypto:<coin-id>" so crypto skus are
# unambiguous and DISJOINT from Costco's numeric skus -> the two sources coexist
# in one time series without a sku collision.
CRYPTO_WATCHLIST: list[dict] = [
    {"source": "bitcoin",  "name": "Bitcoin (BTC)",  "tag": "crypto", "target": 2_600_000},
    {"source": "ethereum", "name": "Ethereum (ETH)", "tag": "crypto", "target": 70_000},
    {"source": "solana",   "name": "Solana (SOL)",   "tag": "crypto", "target": 2_500},
]


def crypto_sku(coin_id: str) -> str:
    """Stable time-series key for a coin: 'crypto:bitcoin'."""
    return f"crypto:{coin_id}"


def fetch_crypto_items(vs_currency: str = DEFAULT_VS, timeout: int = DEFAULT_TIMEOUT,
                       live: bool = True,
                       watchlist: list[dict] | None = None) -> list[dict]:
    """One bulk CoinGecko fetch -> item dicts for the time-series layer.

    live=True (default): a single bulk request for every coin. On ANY failure
    (no network / rate-limit / empty response) it falls back to the
    deterministic `simulate()` stand-in PER COIN, so the call NEVER raises and a
    no-network run still yields a usable price.

    Each item is shaped for `history.append_real` and carries the
    `source`/`synthetic` pair that lets crypto coexist in the same layer:
        {sku, name, tag:'crypto', price, currency, source:'coingecko',
         synthetic: 0 (live) / 1 (fallback), target, url, asset}
    """
    wl = watchlist or CRYPTO_WATCHLIST
    assets = [w["source"] for w in wl]
    bulk: dict = {}
    if live:
        try:
            bulk = fetch_crypto_prices(assets, vs_currency=vs_currency, timeout=timeout)
        except Exception:      # noqa: BLE001 — offline must never crash the pipeline
            bulk = {}
    # An empty `bulk` means no live price came back (no network / rate-limit /
    # empty 200), so every coin below falls back to a deterministic stand-in.

    items: list[dict] = []
    for w in wl:
        live_price = bulk.get(w["source"])
        is_real = live_price is not None
        price = live_price if is_real else simulate(crypto_sku(w["source"]))
        items.append({
            "sku": crypto_sku(w["source"]),
            "name": w.get("name") or w["source"],
            "tag": w.get("tag", "crypto"),
            "price": round(float(price), 4),
            "currency": vs_currency.upper(),
            "source": SOURCE,
            "synthetic": 0 if is_real else 1,
            "target": w.get("target"),
            "url": f"https://www.coingecko.com/en/{w['source']}",
            "asset": w["source"],
        })
    return items


def append_crypto(items: list[dict] | None = None, today: str | None = None,
                  persist_path: str | None = None,
                  live: bool = True, vs_currency: str = DEFAULT_VS,
                  timeout: int = DEFAULT_TIMEOUT) -> int:
    """Append today's crypto observation(s) to the SAME history_data.json.

    Fetches (when `items` is not given) and grows the shared series with one
    point per coin under source='coingecko'. Re-running the same day is a no-op
    (deduped by sku+date+source), so crypto grows the one file beside costco.
    Offline: a failed live fetch yields per-coin synthetic points (never raises,
    and — being synthetic — never trips the real-only alert scanner).
    Returns the new points added.
    """
    if items is None:
        items = fetch_crypto_items(vs_currency=vs_currency, timeout=timeout, live=live)
    return history.append_real(
        items,
        today=today,
        persist_path=persist_path or history.PERSIST_PATH,
        source=SOURCE,
    )


def ensure_crypto_series(persist_path: str | None = None, days: int = 14) -> int:
    """Guarantee a deterministic coingecko backfill exists in the JSON SSOT.

    This is the crypto answer to `history.__main__`'s costco bootstrap: a fresh
    checkout immediately has a crypto movement + verdict to show, coexisting with
    Costco. Idempotent — any coin that already has a series is left untouched —
    so the artifact doesn't churn on re-run. Returns new points added.

    The rewrite goes through `history.dump_observations` — the SAME deterministic
    (sku, observed_at, synthetic) ordering `append_real` uses — not a SQL-reordering
    exporter, so history_data.json stays append-only + human-diffable: existing
    rows keep their place and the new coingecko points are slotted in.
    """
    pp = persist_path or history.PERSIST_PATH
    obs = history.load_observations(pp)
    have = {str(o["sku"]) for o in obs}
    missing = [it for it in fetch_crypto_items(live=False) if it["sku"] not in have]
    if not missing:
        return 0
    c = history.connect(":memory:")
    history.replay(c, obs)                                   # existing obs (costco/…)
    added = history.seed_from_snapshot(missing, conn=c, source=SOURCE, days=days)
    if added:
        rows = [dict(r) for r in c.execute(
            "SELECT sku,name,tag,price,currency,observed_at,source,synthetic "
            "FROM observations").fetchall()]
        for r in rows:
            r["sku"] = str(r["sku"])
        history.dump_observations(rows, pp)
    c.close()
    return added


if __name__ == "__main__":
    # `python crypto.py` : bootstrap the coingecko series into the JSON SSOT
    # (offline-safe: only touches the artifact when a coin is missing).
    n = ensure_crypto_series()
    print(f"coingecko: {n} new points in {history.PERSIST_PATH}")
