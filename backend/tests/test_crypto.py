"""Crypto -> time-series integration tests (#3) — ALL offline, no network.

These pin the issue's acceptance criteria:
  * AC1  the series gets coingecko points (source='coingecko'),
  * AC3  a crypto metric goes through the SAME price_verdict rule as costco,
  * AC5  a no-network run returns the fallback price and does NOT crash, and
  * AC7  coingecko + costco coexist in the SAME history_data.json,
        the SAME series, and the SAME verdict layer.

The offline-fallback tests are the sacred invariant: a failed live fetch yields
a per-coin fallback marked `synthetic=1`, which the real-only alert scanner
(`alerts.alert_for`) can never fire on.
"""
from datetime import datetime

import history
import crypto


# --------------------- live vs fallback ---------------------

def test_live_bulk_fetch_marks_points_real(monkeypatch):
    monkeypatch.setattr(
        crypto, "fetch_crypto_prices",
        lambda assets, vs_currency="twd", timeout=15: {
            "bitcoin": 2600000.0, "ethereum": 72000.0, "solana": 2800.0,
        },
    )
    items = crypto.fetch_crypto_items()
    by = {it["sku"]: it for it in items}
    assert by["crypto:bitcoin"]["price"] == 2600000.0
    assert by["crypto:bitcoin"]["synthetic"] == 0          # live => real
    assert by["crypto:bitcoin"]["source"] == "coingecko"
    assert by["crypto:bitcoin"]["tag"] == "crypto"
    assert by["crypto:bitcoin"]["currency"] == "TWD"
    assert by["crypto:bitcoin"]["sku"] == "crypto:bitcoin"


def test_offline_fetch_returns_fallback_and_does_not_crash(monkeypatch):
    """AC5 / the sacred invariant: network down -> fallback, never a crash."""
    def boom(assets, vs_currency="twd", timeout=15):
        raise OSError("network is down")

    monkeypatch.setattr(crypto, "fetch_crypto_prices", boom)
    items = crypto.fetch_crypto_items()          # must NOT raise
    assert len(items) == len(crypto.CRYPTO_WATCHLIST)
    for it in items:
        assert it["price"] > 0
        assert it["source"] == "coingecko"
        assert it["synthetic"] == 1              # fallback => not real => alert-safe
        assert it["sku"].startswith("crypto:")


def test_offline_empty_response_falls_back_per_coin(monkeypatch):
    """A 200 response with no usable data still falls back per coin, no crash."""
    monkeypatch.setattr(crypto, "fetch_crypto_prices", lambda *a, **k: {})
    items = crypto.fetch_crypto_items()
    assert len(items) == 3
    assert all(it["synthetic"] == 1 and it["price"] > 0 for it in items)


def test_partial_response_falls_back_only_missing_coins(monkeypatch):
    """Present coins stay real (synthetic=0); absent ones become fallback (1)."""
    monkeypatch.setattr(
        crypto, "fetch_crypto_prices",
        lambda assets, vs_currency="twd", timeout=15: {"bitcoin": 2600000.0},
    )
    items = crypto.fetch_crypto_items()
    by = {it["sku"]: it for it in items}
    assert by["crypto:bitcoin"]["synthetic"] == 0
    assert by["crypto:ethereum"]["synthetic"] == 1
    assert by["crypto:solana"]["synthetic"] == 1


def test_offline_fallback_is_deterministic(monkeypatch):
    monkeypatch.setattr(crypto, "simulate", lambda src: 12345.67)
    a = crypto.fetch_crypto_items(live=False)
    b = crypto.fetch_crypto_items(live=False)
    assert a == b                                   # no time/network => identical
    assert all(it["synthetic"] == 1 and it["price"] == 12345.67 for it in a)


# --------------------- coexistence in the SAME series/JSON (AC1 + AC7) ---------------------

def test_coingecko_points_coexist_with_costco_in_same_json(tmp_path):
    art = str(tmp_path / "h.json")
    # 1) backfill a costco series into the artifact
    c = history.connect(":memory:")
    history.seed_from_snapshot(
        [{"sku": "139339", "name": "PQI 35W", "price": 959.0, "tag": "3C"}],
        conn=c, source="backfill",
    )
    history.export_observations(c, art)
    c.close()
    # 2) grow coingecko points in the SAME file
    added = crypto.append_crypto(
        items=[{"sku": "crypto:bitcoin", "name": "Bitcoin (BTC)", "tag": "crypto",
                "price": 2600000.0, "currency": "TWD", "source": "coingecko", "synthetic": 0}],
        today="2026-11-12", persist_path=art,
    )
    assert added == 1
    obs = history.load_observations(art)
    sources = {o["source"] for o in obs}
    assert "backfill" in sources        # the costco side is preserved
    assert "coingecko" in sources       # the crypto side coexists in the same file
    # both series read back out of one DB (the same time-series layer)
    g = history.connect(":memory:")
    history.replay(g, obs)
    skus = history.all_sellers(g)
    assert "139339" in skus and "crypto:bitcoin" in skus
    assert history.series("crypto:bitcoin", conn=g)[0][2] == "coingecko"
    g.close()


def test_append_crypto_idempotent_same_day(tmp_path):
    art = str(tmp_path / "h.json")
    history.dump_observations([], art)
    items = [{"sku": "crypto:bitcoin", "name": "BTC", "tag": "crypto",
              "price": 2600000.0, "currency": "TWD", "source": "coingecko", "synthetic": 0}]
    assert crypto.append_crypto(items=items, today="2026-11-12", persist_path=art) == 1
    assert crypto.append_crypto(items=items, today="2026-11-12", persist_path=art) == 0  # dedup
    assert crypto.append_crypto(items=items, today="2026-11-13", persist_path=art) == 1   # new day


def test_crypto_backfill_is_deterministic_and_tagged(tmp_path):
    a = history.connect(str(tmp_path / "a.db"))
    b = history.connect(str(tmp_path / "b.db"))
    items = [{"sku": "crypto:bitcoin", "name": "BTC", "tag": "crypto",
              "price": 2600000.0, "currency": "TWD"}]
    now = datetime(2026, 11, 11)
    history.seed_from_snapshot(items, conn=a, source="coingecko", now=now)
    history.seed_from_snapshot(items, conn=b, source="coingecko", now=now)
    sa = history.series("crypto:bitcoin", conn=a)
    sb = history.series("crypto:bitcoin", conn=b)
    assert sa == sb                       # identical across two DBs (seeded by sku)
    assert len(sa) == 14
    assert all(src == "coingecko" for (_, _, src) in sa)   # every point carries the source
    a.close()
    b.close()


# --------------------- multi-source ensure_history (AC3 + AC7) ---------------------

def test_ensure_history_backfills_crypto_alongside_costco(tmp_path, monkeypatch):
    """One DB gets a costco series AND a crypto series (the coexistence layer)."""
    monkeypatch.setattr(history, "DEFAULT_DB", str(tmp_path / "h.db"))
    art = str(tmp_path / "h.json")        # empty artifact
    conn = history.ensure_history(
        persist_path=art,
        fallback_items=[{"sku": "1", "name": "W", "price": 100.0, "tag": "家電"}],
        crypto_items=crypto.fetch_crypto_items(live=False),
    )
    skus = history.all_sellers(conn)
    assert "1" in skus and "crypto:bitcoin" in skus
    assert history.series("crypto:bitcoin", conn=conn)[0][2] == "coingecko"
    conn.close()


def test_ensure_crypto_series_bootstraps_then_noops(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DEFAULT_DB", str(tmp_path / "h.db"))
    art = str(tmp_path / "h.json")
    c = history.connect(":memory:")
    history.seed_from_snapshot([{"sku": "111", "name": "C", "price": 50.0, "tag": "3C"}], conn=c)
    history.export_observations(c, art)
    c.close()
    assert crypto.ensure_crypto_series(persist_path=art) > 0        # bootstrap
    assert crypto.ensure_crypto_series(persist_path=art) == 0       # idempotent noop
    obs = history.load_observations(art)
    sources = {o["source"] for o in obs}
    assert "coingecko" in sources     # crypto added
    assert "backfill" in sources      # costco preserved in the same file


# --------------------- crypto goes through the SHARED verdict rule (AC3) ---------------------

def test_crypto_series_feeds_the_shared_verdict_rule(tmp_path, monkeypatch):
    """A coingecko series is judged by the SAME price_verdict as costco."""
    monkeypatch.setattr(crypto, "simulate", lambda src: 2_600_000.0)  # keep the file offline-safe
    art = str(tmp_path / "h.json")
    history.dump_observations([], art)
    # a good-deal shape: high first, a lower low, current in between (20% off high,
    # not at the low) -> the shared rule must call it 'good_deal'.
    for ts, price in (("2026-11-08", 3_000_000.0),
                      ("2026-11-11", 2_200_000.0),
                      ("2026-11-12", 2_400_000.0)):
        history.append_real(
            [{"sku": "crypto:ethereum", "name": "Ethereum (ETH)", "tag": "crypto",
              "price": price, "currency": "TWD", "source": "coingecko", "synthetic": 0}],
            today=ts, persist_path=art,
        )
    from models import price_verdict
    g = history.connect(":memory:")
    history.replay(g, history.load_observations(art))
    m = history.metrics("crypto:ethereum", conn=g)
    v = price_verdict(m)
    assert v["verdict"] == "good_deal"          # crypto used the SAME costco rule
    assert m["current"] == 2400000.0
    assert m["current_is_real"] is True
    g.close()
