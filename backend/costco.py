"""
Costco TW scraper — pull a *basket* of products from a category landing page.

Real HTML scraping with BeautifulSoup (the standard tool). Costco.com.tw
server-renders its main product grid (~10 tiles); each tile has an item-name,
an item-price, and a link whose path is the category breadcrumb:

    /Televisions-Appliances/TV-Home-Entertainment/../p/161087
        ├── 3C/家電 breadcrumb ──┘        └── sku ─┘

So one basket = fetch a couple of category pages, parse their tiles, dedupe by
sku, and tag each with its category.
"""
from __future__ import annotations
import re
import time
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
BASE = "https://www.costco.com.tw"

# Category keywords -> canonical tag, so we can filter a basket to 3C / 家電.
CATEGORY_TAGS = {
    "家電": ("appliance", ("Appliance", "家电", "廚房", "生活家電", "大型家電", "影音家電", "季節家電")),
    "3C": ("3c", ("Digital", "Mobile", "iPad", "Laptop", "Computer", "Periph", "3C", "3c")),
}


def fetch(url: str, timeout: int = 20, retries: int = 3) -> str | None:
    """GET HTML with a browser UA + 429/5xx backoff. Returns text or None."""
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
            return None
        except (urllib.error.URLError, TimeoutError):
            return None
    return None


def _parse_price(text: str):
    """' $1,234.56 ' -> 1234.56 ; returns None if no number found."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*)(?:\.(\d{1,2}))?", text)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(",", ""))
        if m.group(2):
            val = int(m.group(1).replace(",", "")) + int(m.group(2)) / 10 ** len(m.group(2))
        return val
    except ValueError:
        return None


def _tag_for(path: str) -> str:
    """Map a PDP link's breadcrumb path to a category tag (家電 / 3C / 其他)."""
    joined = " ".join(path.split("/"))
    for label, (tag, kws) in CATEGORY_TAGS.items():
        for kw in kws:
            if kw in joined:
                return label
    return "其他"


def parse_products(html: str, base: str = BASE) -> list[dict]:
    """Extract a list of product dicts from a category page's HTML.

    Each dict: {name, price (float|None), currency, url, sku, tag}
    Robust to selector drift: tries item-name/item-price, then falls back.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    tiles = soup.select(".product-item")
    out = []
    for t in tiles:
        # PDP link: first href containing /p/<sku>
        link = None
        for a in t.select("a[href]"):
            h = a.get("href")
            if h and "/p/" in h:
                link = h
                break
        sku = None
        if link:
            m = re.search(r"/p/([0-9A-Za-z]+)", link)
            sku = m.group(1) if m else None
        # name: dedicated item-name, else a heading, else the image alt,
        # else the first chunk of visible text.
        name = None
        el = t.select_one(".item-name")
        if el and el.get_text(strip=True):
            name = el.get_text(strip=True)
        else:
            for cand in [
                t.select_one("h1,h2,h3"),
                t.select_one("img[alt]"),
            ]:
                if cand:
                    txt = cand.get_text(strip=True) or (cand.get("alt") or "").strip()
                    if txt:
                        name = txt
                        break
        if name is None:
            visible = t.get_text(" ", strip=True)
            name = visible or None
        # price
        price = None
        pel = t.select_one(".item-price")
        if pel:
            price = _parse_price(pel.get_text(" ", strip=True))
        if name is None and link is None:
            continue
        path = link or ""
        out.append(
            {
                "name": (name or "").strip() or "（無名）",
                "price": price,
                "currency": "TWD",
                "url": (base + link) if link else None,
                "sku": sku,
                "tag": _tag_for(path),
                "category_path": path.lstrip("/"),
            }
        )
    return out


def scrape_category(url: str, timeout: int = 20) -> list[dict]:
    """Fetch a category landing page and return its products."""
    html = fetch(url, timeout=timeout)
    return parse_products(html)


def filter_basket(products: list[dict], tags=None) -> list[dict]:
    """Keep only products whose tag is in `tags` (default: 3C + 家電)."""
    if tags is None:
        tags = {"家電", "3C"}
    return [p for p in products if p["tag"] in tags]


# ---- 家電 basket via bounded BFS crawl of PDP "相關推薦" links ----------------
# Costco's rendered catalog caps at ~30 featured items (家电 only ~3). But each
# 家電 PDP lists "相關推薦" links to MORE 家電 PDPs. A bounded BFS crawl of those
# links grows the 家電 basket. This is the standard technique when a listing
# page is intentionally sparse: crawl outward through the product graph.
#
# `scrape_costco` is imported lazily inside crawl_appliances so that
# `import costco` does NOT pull in the `requests` dependency at module load time.


def pdp_name(html: str) -> str | None:
    """Pull the human product name from a single PDP's og:title, stripping the
    ' | Costco 好市多' suffix."""
    m = re.search(r'property="og:title"[^>]*content="([^"]+)"', html)
    if not m:
        return None
    name = m.group(1)
    for suf in ("| Costco 好市多", " | Costco", "| 好市多", " | "):
        if name.endswith(suf):
            name = name[: -len(suf)]
            break
    return name.strip() or None


def related_appliance_urls(html: str) -> list[str]:
    """Extract 家電-tagged related-PDP URLs from a PDP's 相關推薦 links.

    Only returns URLs whose breadcrumb path the tagger classifies as 家電, so
    the crawl stays on the 家電 subtree.
    """
    urls, seen = [], set()
    for path in re.findall(r'(/(?:[A-Za-z0-9._-]+/)*p/[0-9A-Za-z]+)', html):
        if _tag_for(path) == "家電":
            u = BASE + path
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


def crawl_appliances(
    seed_urls: list[str],
    max_items: int = 15,
    max_requests: int = 40,
    timeout: int = 20,
    delay: float = 0.3,
) -> list[dict]:
    """BFS crawl 家電 PDPs outward through their 相關推薦 links.

    Returns up to `max_items` 家電 products (each with name, price, sku, url,
    path). Bounded by `max_requests` + a polite delay between requests.
    """
    import time
    from collections import deque
    from scrapers import scrape_costco  # lazy: import costco shouldn't need requests

    queue = deque(seed_urls)
    seen = set()
    basket: list[dict] = []
    requests = 0

    while queue and len(basket) < max_items and requests < max_requests:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        html = fetch(url, timeout=timeout)
        requests += 1
        time.sleep(delay)
        if not html:
            continue
        info = scrape_costco(url, timeout=timeout)  # {price, sku, currency, ...}
        sku = info.get("sku") if info else None
        name = pdp_name(html)
        # Enqueue related 家電 PDPs before consuming the basket cap.
        for ru in related_appliance_urls(html):
            if ru not in seen:
                queue.append(ru)
        if sku and info.get("price") and name:
            if sku and sku not in {b["sku"] for b in basket}:
                basket.append(
                    {
                        "name": name,
                        "price": info["price"],
                        "currency": info.get("currency", "TWD"),
                        "sku": sku,
                        "url": url,
                        "tag": "家電",
                        "category_path": url.lstrip("/"),
                    }
                )
    return basket


# ---- 3C + 家電 合併一籃 -----------------------------------------------------------

from costco_data import DEMO_BASKET


def basket(live: bool = False,
           max_appliance_items: int = 15, delay: float = 0.3) -> list[dict]:
    """Return a combined 3C + 家電 basket.

    live=False (default): returns today's pre-snapshotted `DEMO_BASKET` —
        fast, offline, safe for tests and CI.
    live=True: real scrape + BFS crawl; ~30s, needs internet.
    """
    if not live:
        return DEMO_BASKET

    seen: set = set()
    out: list[dict] = []

    for pg in ("/c/1", "/c/3"):
        for p in scrape_category(f"{BASE}{pg}"):
            if p["sku"] and p["sku"] not in seen and p.get("price") and p["name"] != "（無名）":
                if _tag_for(p.get("category_path", "") or "") == "3C":
                    seen.add(p["sku"])
                    out.append(p)

    seed_urls = [
        f"{BASE}/Televisions-Appliances/TV-Home-Entertainment/Soundbars-Home-Theater/BOSE-Solo-Soundbar-TV-Speaker-II/p/3062725",
        f"{BASE}/Televisions-Appliances/TV-Home-Entertainment/Television/Philips-55-inch-4K-UHD-Smart-TV/p/153526",
        f"{BASE}/Televisions-Appliances/Air-Conditioners-Fans/Coolers-Humidifiers/Honeywell-Air-Purifier-AC1025D/p/157137",
    ]
    for p in crawl_appliances(seed_urls, max_items=max_appliance_items,
                                max_requests=50, delay=delay):
        if p["sku"] not in seen:
            seen.add(p["sku"])
            out.append(p)
    return out


if __name__ == "__main__":
    import sys
    live = "--live" in sys.argv
    items = basket(live=live)
    c3 = [p for p in items if p.get("tag") == "3C"]
    ca = [p for p in items if p.get("tag") == "家電"]
    mode = "live" if live else "DEMO_BASKET (offline)"
    print(f"3C/家電 一籃 [{mode}] — 3C {len(c3)} + 家電 {len(ca)} = {len(items)} 筆")
    for t, items_t in (("3C", c3), ("家電", ca)):
        print(f"\n【{t}】{len(items_t)} 筆")
        for p in sorted(items_t, key=lambda x: -(x.get('price') or 0)):
            print(f'  NT${p["price"]:>10,.2f}  {p["name"][:44]:<44}  sku {p["sku"]}')
