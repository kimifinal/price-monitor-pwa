"""
Demo runner: fetch LIVE prices and apply the monitor rule, print a watchlist.

    python demo.py               # scrape the live Costco product page
    python demo.py --no-fetch    # force the offline simulator (CI-safe)

This is the "let me look at the data" entry point.
"""
from models import should_alert
from scrapers import scrape_costco, simulate
import sys

# A sample watchlist: a real Costco product (HTML scrape). Target set so the mix
# is illustrative — below vs. above target.
COSTCO_URL = "https://www.costco.com.tw/Food-Dining/Drinks/Beverages-Juice/Tree-Top-Apple-Juice-2-L-X-4-Pack/p/30991"

WATCHLIST = [
    {"name": "Tree Top 蘋果汁 2L×4", "kind": "costco", "source": COSTCO_URL, "target": 480},  # 低於 480 ->  🔔
]


def main():
    no_fetch = "--no-fetch" in sys.argv
    label = "模擬價（離線 fallback）" if no_fetch else "真實現價（Costco HTML 抓取）"
    print(f"# Price Monitor  --  {label}\n")
    print(f"{'品名':<24}{'目標':>9}{'現價':>14}{'狀態':>10}")
    print("-" * 60)

    alerts = 0
    for item in WATCHLIST:
        if item["kind"] == "costco":
            if no_fetch:
                price = simulate(item["name"])
                extra = "  模擬價"
            else:
                data = scrape_costco(item["source"], timeout=15)
                price = data["price"] if data else None
                if data:
                    extra = f"  TWD · sku {data['sku']} · 庫存 {data['availability'].split('/')[-1]}"
                else:
                    extra = "  抓取失敗，回退模擬"
                    price = simulate(item["name"])
        else:  # a non-costco kind falls back to the deterministic simulator
            price = simulate(item["source"])
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
