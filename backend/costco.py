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


if __name__ == "__main__":
    # 3C/家電 一籃。
    # NOTE(follow-up): 家電分頁 /c/301 /c/305 /c/308 是 lazy/JS render，
    #   抓到的卡片是空骨架（pin 正確但 name/price 要 JS 才填）。
    #   要補齊家電籃，下一步需 browser_exec 渲染該分頁後回寫解析。
    #   目前 3C 是 server-side render，HTTP 直抓即可；家電暫缺。
    pages = ["/c/1", "/c/3", "/c/301", "/c/305", "/c/308"]  # 3C + 各類家電 landing
    seen, products = set(), []
    for pg in pages:
        for p in scrape_category(f"{BASE}{pg}"):
            key = p["sku"]
            if key and key not in seen:
                seen.add(key)
                products.append(p)

    # Keep only genuine 3C/家电 tiles that have BOTH a name and a price
    # (drops cross-sell carousels like 紙巾/濾水壺 and un-parsed carousel tiles).
    clean = [p for p in filter_basket(products) if p["price"] and p["name"] != "（無名）"]

    clean.sort(key=lambda p: (p["tag"], -(p["price"] or 0)))
    print(f"3C / 家電 一籃 — 抓到 {len(clean)} 筆有效商品（含品名 + 價格）\n")
    for t in ("3C", "家電"):
        items = [p for p in clean if p["tag"] == t]
        if not items:
            continue
        print(f"【{t}】{len(items)} 筆")
        for p in items:
            path = p["category_path"].split("/")
            crumb = " > ".join(path[:2]) if len(path) > 1 else p["category_path"]
            print(f"  NT${p['price']:>10,.2f}  {p['name']:<46} sku {p['sku']}")
            print(f"             {crumb}")
    if clean:
        hi = max(clean, key=lambda p: p["price"])
        lo = min(clean, key=lambda p: p["price"])
        print(f"\n最貴: {hi['name']}  NT${hi['price']:,.2f}")
        print(f"最平: {lo['name']}  NT${lo['price']:,.2f}")
