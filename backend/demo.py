"""
Demo runner: fetch LIVE prices and apply the monitor rule, print a watchlist.

    python demo.py               # one bulk request to CoinGecko (live TWD)
    python demo.py --no-fetch    # force the offline simulator (CI-safe)

This is the "let me look at the data" entry point.
"""
from models import should_alert
from scrapers import fetch_crypto_prices, simulate
import sys

# A sample watchlist: asset + the price target that should trigger an alert.
# Targets are set so the mix is illustrative — some should alert, some should wait.
WATCHLIST = [
    {"name": "Bitcoin (BTC)", "source": "crypto:bitcoin", "target": 2_600_000},  # above market -> 待價
    {"name": "Ethereum (ETH)", "source": "crypto:ethereum", "target": 70_000},    # ~ at/below ->  🔔
    {"name": "Solana (SOL)", "source": "crypto:solana", "target": 2_500},         # above market -> 待價
]


def asset_of(item: dict) -> str:
    return item["source"].split(":", 1)[1]


def main():
    no_fetch = "--no-fetch" in sys.argv
    assets = [asset_of(w) for w in WATCHLIST]

    print(f"# Price Monitor  --  "
          + ("模擬價（離線 fallback）" if no_fetch else "真實行價 CoinGecko/TWD\n"))
    print(f"{'品名':<18}{'目標價':>12}{'現價':>16}{'狀態':>10}")
    print("-" * 56)

    # ONE request for all assets (avoids per-asset rate-limit trips).
    if no_fetch:
        prices = {a: simulate(f"__sim__{a}") for a in assets}
    else:
        try:
            prices = fetch_crypto_prices(assets, vs_currency="twd", timeout=15)
        except Exception as e:  # noqa: BLE001  demo degrades, never crashes
            print(f"[network] 抓取失敗，回退模擬價: {e}\n")
            prices = {a: simulate(f"__sim__{a}") for a in assets}

    alerts = 0
    for item in WATCHLIST:
        price = prices.get(asset_of(item))
        if price is None:
            print(f"{item['name']:<18}{item['target']:>12,.0f}{'— 無資料':>16}")
            continue
        hot = should_alert(price, item["target"])
        flag = "🔔 跌破" if hot else "待價"
        if hot:
            alerts += 1
        print(f"{item['name']:<18}{item['target']:>12,.0f}{price:>16,.2f}{flag:>10}")

    print("-" * 56)
    print(f"{alerts} 筆低於目標價 → 觸發警報" if alerts else "無跌破，全數待價")


if __name__ == "__main__":
    main()
