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


# ---- Unified 3C + 家電 basket via bounded BFS crawl of PDP "相關推薦" links ----
# Costco's rendered catalog caps at ~30 featured items per tag, but each PDP lists
# "相關推薦" links to MORE same-category PDPs. A bounded BFS crawl of those links
# grows the basket for any tag (3C or 家電). This is the standard technique when a
# listing page is intentionally sparse: crawl outward through the product graph.
#
# `parse_offers` is imported lazily inside `crawl_basket` so that `import costco`
# does NOT pull in `scrapers`/`requests` at module load time (keeps the offline
# DEMO_BASKET path dependency-light).


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


def crawl_basket(
    seed_urls: list[str],
    tag: str,
    max_items: int = 20,
    max_requests: int = 40,
    timeout: int = 5,
    delay: float = 0.1,
    workers: int = 8,
) -> list[dict]:
    """BFS-crawl PDPs outward through their 相關推薦 links, keeping only items
    whose breadcrumb path classifies as `tag` (家電 or 3C).

    Two speed levers, both applied here:
      1. **Parallel rounds** — each round fetches up to `workers` PDPs at once
         via a ThreadPoolExecutor (BFS is still level-by-level, so the order
         and early-exit semantics are preserved). This is the big win vs a
         naïve sequential crawl.
      2. **Single fetch per PDP** — `parse_offers` runs on the HTML we already
         fetched; `scrape_costco` re-fetches and is 2× slower, so we don't use
         it. A short per-request `timeout` (5s) bounds the dead-link tail instead
         of waiting 15–20s each (the dead-link tail was the real bottleneck).
    The polite `delay` is per-round, not per-request, so wall time ≈
        ceil(max_requests / workers) × (fetch + delay).
    `parse_offers` is imported lazily so `import costco` doesn't pull in the
    `requests` dependency at module load (keeps the offline DEMO_BASKET path
    dependency-light).
    """
    import time
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor
    from scrapers import parse_offers

    queue = deque(seed_urls)
    seen = set()
    basket: list[dict] = []
    requests = 0

    while queue and len(basket) < max_items and requests < max_requests:
        # Collect this round's work — up to `workers` fresh URLs, respecting the
        # remaining request budget.
        round_urls: list[str] = []
        while queue and len(round_urls) < workers and requests + len(round_urls) < max_requests:
            u = queue.popleft()
            if u in seen:
                continue
            seen.add(u)
            round_urls.append(u)
        if not round_urls:
            break

        # Parallel fetch of this level (the network part only; parsing below runs
        # in the main thread so shared state has no races).
        def _fetch(u: str):
            return u, fetch(u, timeout=timeout)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            fetched = list(ex.map(_fetch, round_urls))

        for url, html in fetched:
            requests += 1
            if not html:
                continue
            name = pdp_name(html)
            m = re.search(r"/p/([0-9A-Za-z]+)", url)
            sku = m.group(1) if m else None
            info = parse_offers(html) or {}
            price = info.get("price")
            currency = info.get("currency") or "TWD"
            # enqueue related PDPs that match our target tag
            for path in re.findall(r"(/(?:[A-Za-z0-9._-]+/)*p/[0-9A-Za-z]+)", html):
                ru = BASE + path
                if ru not in seen and _tag_for(path) == tag:
                    queue.append(ru)
            if sku and price is not None and name and sku not in {b["sku"] for b in basket}:
                basket.append(
                    {
                        "name": name,
                        "price": price,
                        "currency": currency,
                        "sku": sku,
                        "url": url,
                        "tag": tag,
                        "category_path": url.lstrip("/"),
                    }
                )
            if len(basket) >= max_items:
                break
        # Polite wait between rounds (not per-request) so parallelism still helps.
        time.sleep(delay)
    return basket


# 家電-specific wrapper (kept for backward compat + existing tests)
def crawl_appliances(
    seed_urls: list[str],
    max_items: int = 15,
    max_requests: int = 40,
    timeout: int = 8,
    delay: float = 0.1,
    workers: int = 4,
) -> list[dict]:
    return crawl_basket(seed_urls, tag="家電", max_items=max_items,
                        max_requests=max_requests, timeout=timeout, delay=delay,
                        workers=workers)


def related_appliance_urls(html: str) -> list[str]:
    """家電-tagged related-PDP URLs from a PDP."""
    urls = []
    seen = set()
    for path in re.findall(r"(/(?:[A-Za-z0-9._-]+/)*p/[0-9A-Za-z]+)", html):
        if _tag_for(path) == "家電":
            u = BASE + path
            if u not in seen:
                seen.add(u)
                urls.append(u)
    return urls


# ---- 3C + 家電 合併一籃 -----------------------------------------------------------

from costco_data import DEMO_BASKET


def basket(live: bool = False,
           per_tag_cap: int = 12, delay: float = 0.1,
           workers: int = 8, timeout: int = 5) -> list[dict]:
    """Return a combined 3C + 家電 basket.

    live=False (default): returns today's pre-snapshotted `DEMO_BASKET` —
        fast, offline, safe for tests and CI.
    live=True: unified parallel BFS crawl seeded from DEMO_BASKET's own PDPs;
        both 3C and 家電 grow outward through their 相關推薦 links. The crawl is
        parallel (PDPs fetched 8-at-a-time + 5s/request timeout), so the fast
        ad-hoc basket lands in ~14s instead of the ~70s a sequential crawl took.
        For an occasional full-coverage refresh, bump `per_tag_cap` (e.g. 15,
        ~3s slower per tag) — that is a scheduled job's job, not ad-hoc latency.
    """
    if not live:
        return DEMO_BASKET

    seen: set = set()
    out: list[dict] = []

    for tag in ("3C", "家電"):
        # Seed each tag's crawl from DEMO_BASKET's PDPs of that tag — keeps the
        # crawl starting points in sync with the last known-good snapshot.
        seeds = [p["url"] for p in DEMO_BASKET
                 if p.get("tag") == tag and p.get("url")][:5]
        for p in crawl_basket(seeds, tag=tag, max_items=per_tag_cap,
                               max_requests=40, timeout=timeout,
                               delay=delay, workers=workers):
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
