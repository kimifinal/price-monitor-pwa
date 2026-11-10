"""
Demo runner: fetch LIVE prices and apply the monitor rule, print a watchlist.

    python demo.py               # watches a few crypto assets in TWD
    python demo.py --no-fetch    # force the offline simulator (CI-safe demo)

This is the "let me look at the data" entry point.
"""
from models import should_alert
from scrapers import fetch_price
import sys

# A sample watchlist: asset + the price target that should trigger an alert.
# Targets are set so the mix is illustrative — some should alert, some should wait.
WATCHLIST = [
    {"name": "Bitcoin (BTC)", "source": "crypto:bitcoin", "target": 2_600_000},  # above market -> 待價
    {"name": "Ethereum (ETH)", "source": "crypto:ethereum", "target": 70_000},    # ~ at/below -> 🔔
    {"name": "Solana (SOL)", "source": "crypto:solana", "target": 2_500},         # above market -> 待價
]


def main():
    no_fetch = "--no-fetch" in sys.argv
    print(f"# Price Monitor  --  {'模擬價' if no_fetch else '真實行價 CoinGecko/TWD'}\n")
    print(f"{'品名':<16}{'目標價':>12}{'現價':>14}{'狀態':>10}")
    print("-" * 52)
    alerts = 0
    for item in WATCHLIST:
        if no_fetch:
            price = fetch_price(f"__sim__{item['source']}", vs_currency="twd", timeout=1)
        else:
            price = fetch_price(item["source"], vs_currency="twd", timeout=15)
        hot = should_alert(price, item["target"])
        flag = "🔔 跌破" if hot else "  待價"
        if hot:
            alerts += 1
        print(
            f"{item['name']:<16}"
            f"{item['target']:>12,.0f}"
            f"{price:>14,.2f}"
            f"{flag:>10}"
        )
    print("-" * 52)
    if alerts:
        print(f"{alerts} 筆低於目標價 → 觸發警報")
    else:
        print("無跌破，全數待價")


if __name__ == "__main__":
    main()
