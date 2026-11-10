"""
Demo runner: fetch LIVE prices and apply the monitor rule, print a watchlist.

    python demo.py               # one bulk request to CoinGecko (live TWD)
    python demo.py --no-fetch    # force the offline simulator (CI-safe)

This is the "let me look at the data" entry point.
"""
from models import should_alert
from scrapers import fetch_crypto_prices, scrape_costco, simulate
import sys

# A sample watchlist: crypto (CoinGecko API) + a real Costco product (HTML
# scrape). Targets set so the mix is illustrative — some alert, some wait.
COSTCO_URL = "https://www.costco.com.tw/Food-Dining/Drinks/Beverages-Juice/Tree-Top-Apple-Juice-2-L-X-4-Pack/p/30991"

WATCHLIST = [
    {"name": "Bitcoin (BTC)", "kind": "crypto", "source": "bitcoin", "target": 2_600_000},  # above market -> 待價
    {"name": "Ethereum (ETH)", "kind": "crypto", "source": "ethereum", "target": 70_000},    # ~ at/below  ->  🔔
    {"name": "Solana (SOL)",   "kind": "crypto", "source": "solana",   "target": 2_500},     # above market -> 待價
    {"name": "Tree Top 蘋果汁 2L×4", "kind": "costco", "source": COSTCO_URL, "target": 480},  # 低於 480 ->  🔔
]


def main():
    no_fetch = "--no-fetch" in sys.argv
    label = "模擬價（離線 fallback）" if no_fetch else "真實行價（CoinGecko API + Costco HTML 抓取）"
    print(f"# Price Monitor  --  {label}\n")
    print(f"{'品名':<24}{'目標':>9}{'現價':>14}{'狀態':>10}")
    print("-" * 60)

    # ONE bulk request for all crypto assets (avoids per-asset rate limits).
    crypto = [i for i in WATCHLIST if i["kind"] == "crypto"]
    bulk = {}
    if crypto and not no_fetch:
        assets = [i["source"] for i in crypto]
        try:
            bulk = fetch_crypto_prices(assets, vs_currency="twd", timeout=15)
        except Exception as e:  # noqa: BLE001
            print(f"[network] crypto 抓取失敗，回退模擬: {e}\n")
            bulk = {}

    alerts = 0
    for item in WATCHLIST:
        if item["kind"] == "costco":
            data = scrape_costco(item["source"], timeout=15)
            price = data["price"] if data else None
            if data:
                extra = f"  TWD · sku {data['sku']} · 庫存 {data['availability'].split('/')[-1]}"
            else:
                extra = "  抓取失敗，回退模擬"
                price = simulate(item["name"])
        else:
            if no_fetch or not bulk:
                price = simulate(f"__sim__{item['source']}")
            else:
                price = bulk.get(item["source"])
            extra = ""
        if price is None:
            print(f"{item['name']:<24}{item['target']:>9,.0f}{'— 無資料':>16}")
            continue
        hot = should_alert(price, item["target"])
        flag = "🔔 跌破" if hot else "待價"
        if hot:
            alerts += 1
        print(f"{item['name']:<24}{item['target']:>9,.0f}{price:>14,.2f}{flag:>10}{extra}")

    print("-" * 60)
    print(f"{alerts} 筆低於目標價 → 觸發警報" if alerts else "無跌破，全數待價")


if __name__ == "__main__":
    main()
