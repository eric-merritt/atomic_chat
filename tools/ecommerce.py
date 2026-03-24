"""Ecommerce tools: eBay, Amazon, Craigslist search and analysis.

Platform tools (6): Direct ecommerce scrapers that return raw structured data.
Flow tools (3): Cross-platform orchestration tools owned by the dispatcher agent.
"""

import os
import re
import json
import time
import random
import urllib.request
import urllib.parse
from typing import Optional

from langchain.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from tools._output import tool_result, retry


# ── eBay Operations ──────────────────────────────────────────────────────────

EBAY_SORT_OPTIONS = {
    "best_match": "",
    "ending_soonest": "&_sop=1",
    "newly_listed": "&_sop=10",
    "price_low": "&_sop=15",
    "price_high": "&_sop=16",
}


def _parse_ebay_listings(html: str) -> list[dict]:
    """Extract listing data from eBay search results HTML (internal helper).

    Supports both the legacy s-item__* layout and the current s-card layout
    (eBay migrated to su-card-container / s-card classes circa late 2025).
    """
    # Restrict to main results river if present
    river_marker = re.search(r'id=["\']?srp-river-results["\']?', html)
    if river_marker:
        html = html[river_marker.start():]

    listings = []

    # ── New layout (s-card) ──────────────────────────────────────────────
    card_starts = [m.start() for m in re.finditer(r'class="s-card\s+s-card--', html)]
    if card_starts:
        for idx, start in enumerate(card_starts):
            end = card_starts[idx + 1] if idx + 1 < len(card_starts) else len(html)
            block = html[start:end]
            listing = {}

            title_match = re.search(
                r'class=s-card__title[^>]*>(.*?)</div>',
                block, re.DOTALL,
            )
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                title = re.sub(r"Opens in a new window or tab$", "", title).strip()
                title = re.sub(r"^New Listing", "", title).strip()
                if title.lower() in ("shop on ebay", "results matching fewer words", ""):
                    continue
                listing["title"] = title

            url_match = re.search(r'href=["\']?(https://www\.ebay\.com/itm/\d+)', block)
            if url_match:
                listing["url"] = url_match.group(1)

            price_spans = re.findall(r's-card__price">(.*?)</span>', block, re.DOTALL)
            if price_spans:
                price_text = " ".join(re.sub(r"<[^>]+>", "", p).strip() for p in price_spans)
                listing["price_text"] = price_text
                nums = re.findall(r"\$?([\d,]+\.?\d*)", price_text)
                if nums:
                    listing["price"] = float(nums[0].replace(",", ""))

            ship_match = re.search(
                r'su-styled-text[^>]*>([^<]*(?:delivery|shipping)[^<]*)</span>',
                block, re.IGNORECASE,
            )
            if ship_match:
                listing["shipping"] = ship_match.group(1).strip()

            if listing.get("title") and listing.get("url"):
                listings.append(listing)

        if listings:
            return listings

    # ── Legacy layout (s-item) ───────────────────────────────────────────
    item_blocks = re.findall(
        r'<div class="s-item__wrapper[^"]*">(.*?)</div>\s*</div>\s*</li>',
        html, re.DOTALL,
    )
    if not item_blocks:
        item_blocks = re.findall(r'class="s-item\s[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)

    for block in item_blocks:
        listing = {}
        title_match = re.search(
            r'class="s-item__title[^"]*"[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</(?:h3|div|span)>',
            block, re.DOTALL,
        )
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
            if title.lower() in ("shop on ebay", "results matching fewer words"):
                continue
            listing["title"] = title

        url_match = re.search(r'href="(https://www\.ebay\.com/itm/[^"]+)"', block)
        if url_match:
            listing["url"] = url_match.group(1).split("?")[0]

        price_match = re.search(r'class="s-item__price[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if price_match:
            price_text = re.sub(r"<[^>]+>", "", price_match.group(1)).strip()
            listing["price_text"] = price_text
            nums = re.findall(r"\$?([\d,]+\.?\d*)", price_text)
            if nums:
                listing["price"] = float(nums[0].replace(",", ""))

        ship_match = re.search(r'class="s-item__shipping[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if ship_match:
            listing["shipping"] = re.sub(r"<[^>]+>", "", ship_match.group(1)).strip()

        if listing.get("title") and listing.get("url"):
            listings.append(listing)
    return listings


@tool
@retry()
def ebay_search(
    query: str,
    sort: str = "best_match",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: str = "",
    max_results: int = 20,
) -> str:
    """Search eBay Buy It Now listings and return parsed results.

    WHEN TO USE: When searching for products on eBay specifically.
    WHEN NOT TO USE: When you want to search multiple platforms at once (use cross_platform_search).

    Args:
        query: Search terms (e.g. "RTX 3060", "mechanical keyboard"). Must be non-empty.
        sort: Sort order. One of: "best_match", "ending_soonest", "newly_listed", "price_low", "price_high".
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        condition: Item condition filter. One of: "new", "used", "refurbished", "parts", or "" to skip.
        max_results: Maximum listings to return. Range: 1-100.

    Output format:
        {"status": "success", "data": {"query": "...", "count": N, "listings": [
            {"title": "...", "url": "...", "price": 123.45, "price_text": "$123.45", "shipping": "..."},
            ...
        ]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}"
    url += EBAY_SORT_OPTIONS.get(sort, "")
    if min_price is not None:
        url += f"&_udlo={min_price}"
    if max_price is not None:
        url += f"&_udhi={max_price}"
    condition_map = {
        "new": "&LH_ItemCondition=1000",
        "used": "&LH_ItemCondition=3000",
        "refurbished": "&LH_ItemCondition=2500",
        "parts": "&LH_ItemCondition=7000",
    }
    if condition.lower() in condition_map:
        url += condition_map[condition.lower()]
    url += "&rt=nc&LH_BIN=1"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return tool_result(error=str(e))

    listings = _parse_ebay_listings(html)[:max_results]
    return tool_result(data={"query": query, "count": len(listings), "listings": listings})


@tool
@retry()
def ebay_sold_search(query: str, max_results: int = 20) -> str:
    """Search eBay completed/sold listings to find market prices.

    WHEN TO USE: When you need historical sold prices for market value analysis.
    WHEN NOT TO USE: When you need currently available listings (use ebay_search instead).

    Args:
        query: Search terms. Must be non-empty.
        max_results: Maximum listings to return. Range: 1-100.

    Output format:
        {"status": "success", "data": {"query": "...", "count": N, "listings": [...]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Complete=1&LH_Sold=1&rt=nc"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return tool_result(error=str(e))

    listings = _parse_ebay_listings(html)[:max_results]
    for listing in listings:
        listing["sold"] = True
    return tool_result(data={"query": query, "count": len(listings), "listings": listings})


# ── GPU model extraction & shipping parsing ──────────────────────────────────

_GPU_MODEL_PATTERNS = [
    re.compile(r"(RTX)\s*(\d0[5-9]0)(\s*Ti|\s*Super)?", re.IGNORECASE),
    re.compile(r"(GTX)\s*(16[56]0)(\s*Ti|\s*Super)?", re.IGNORECASE),
    re.compile(r"(Quadro\s*RTX\s*[4-8]000)", re.IGNORECASE),
    re.compile(r"\b(A100|A6000|A5000|A4000|A40|A30|A10)\b", re.IGNORECASE),
    re.compile(r"\b(L40S|L40)\b", re.IGNORECASE),
    re.compile(r"\b(H200|H100)\b", re.IGNORECASE),
    re.compile(r"\b(B200|B100|GB200)\b", re.IGNORECASE),
    re.compile(r"\b(T4)\b"),
]


def _extract_gpu_model(title: str) -> str:
    """Extract a normalized GPU model name from a listing title."""
    for pat in _GPU_MODEL_PATTERNS:
        m = pat.search(title)
        if m:
            groups = [g.strip() for g in m.groups() if g]
            model = " ".join(groups)
            model = re.sub(r"(RTX|GTX)\s*(\d)", r"\1 \2", model, flags=re.IGNORECASE)
            model = re.sub(r"\s+", " ", model).strip()
            return model.upper()
    return ""


def _parse_shipping_cost(shipping: str) -> float:
    """Parse a shipping string into a numeric cost."""
    if not shipping:
        return 0.0
    shipping_lower = shipping.lower()
    if "free" in shipping_lower:
        return 0.0
    m = re.search(r"\$?([\d,]+\.?\d*)", shipping)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


@tool
@retry()
def ebay_deep_scan(
    query: str,
    condition: str = "used",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "best_match",
    pages: int = 5,
    max_results: int = 200,
) -> str:
    """Paginated eBay search that compresses results to model + price for bulk analysis.

    WHEN TO USE: When you need a large dataset of eBay listings for price analysis or comparison.
    WHEN NOT TO USE: When you only need a quick search (use ebay_search instead).

    Scrapes multiple pages with rate-limiting delays, extracts GPU model names,
    parses shipping costs, deduplicates by URL, and returns compact listings
    sorted by model then total cost.

    Args:
        query: Search terms (e.g. "RTX 3060", "used GPU"). Must be non-empty.
        condition: Filter. One of: "new", "used", "refurbished", "parts", or "" to skip.
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        sort: Sort order. One of: "best_match", "ending_soonest", "newly_listed", "price_low", "price_high".
        pages: Number of result pages to scrape. Range: 1-10.
        max_results: Maximum total listings to return. Range: 1-500.

    Output format:
        {"status": "success", "data": {"query": "...", "pages_scraped": N, "count": N, "listings": [...]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    pages = max(1, min(pages, 10))

    encoded = urllib.parse.quote_plus(query)
    base_url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}"
    base_url += EBAY_SORT_OPTIONS.get(sort, "")
    if min_price is not None:
        base_url += f"&_udlo={min_price}"
    if max_price is not None:
        base_url += f"&_udhi={max_price}"
    condition_map = {
        "new": "&LH_ItemCondition=1000",
        "used": "&LH_ItemCondition=3000",
        "refurbished": "&LH_ItemCondition=2500",
        "parts": "&LH_ItemCondition=7000",
    }
    if condition.lower() in condition_map:
        base_url += condition_map[condition.lower()]
    base_url += "&rt=nc&LH_BIN=1"

    seen_urls = set()
    all_listings = []

    for page_num in range(1, pages + 1):
        url = base_url if page_num == 1 else f"{base_url}&_pgn={page_num}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:
            if page_num < pages:
                time.sleep(random.uniform(3.0, 6.0))
            continue

        raw_listings = _parse_ebay_listings(html)

        for listing in raw_listings:
            item_url = listing.get("url", "")
            if not item_url or item_url in seen_urls:
                continue
            seen_urls.add(item_url)

            price = listing.get("price", 0.0)
            shipping_cost = _parse_shipping_cost(listing.get("shipping", ""))
            model = _extract_gpu_model(listing.get("title", ""))

            all_listings.append({
                "model": model,
                "title": listing.get("title", ""),
                "price": price,
                "shipping_cost": shipping_cost,
                "total_cost": round(price + shipping_cost, 2),
                "url": item_url,
            })

        if page_num < pages:
            time.sleep(random.uniform(3.0, 6.0))

    all_listings.sort(key=lambda x: (x["model"], x["total_cost"]))

    return tool_result(data={
        "query": query,
        "pages_scraped": pages,
        "count": len(all_listings[:max_results]),
        "listings": all_listings[:max_results],
    })


# ── Amazon Operations ─────────────────────────────────────────────────────────

def _parse_amazon_listings(html: str) -> list[dict]:
    """Extract listing data from Amazon search results HTML (internal helper)."""
    listings = []

    blocks = re.findall(
        r'data-component-type="s-search-result"[^>]*data-asin="([^"]+)"(.*?)(?=data-component-type="s-search-result"|<div class="s-main-slot s-result-list-col-0-footer">|$)',
        html, re.DOTALL,
    )
    if not blocks:
        blocks = re.findall(
            r'data-asin="([A-Z0-9]{10})"(.*?)(?=data-asin="[A-Z0-9]{10}"|$)',
            html, re.DOTALL,
        )

    for asin, block in blocks:
        if not asin or asin == "":
            continue
        listing: dict = {"asin": asin}

        title_match = re.search(
            r'<span class="a-(?:size-medium a-color-base a-text-normal|text-normal)"[^>]*>(.*?)</span>',
            block, re.DOTALL,
        )
        if not title_match:
            title_match = re.search(r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.DOTALL)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
            if not title or title.lower() in ("", "sponsored"):
                continue
            listing["title"] = title
        else:
            continue

        url_match = re.search(r'href="(/[^"]*?/dp/[A-Z0-9]{10}[^"]*)"', block)
        if url_match:
            listing["url"] = "https://www.amazon.com" + url_match.group(1).split("/ref=")[0]
        else:
            listing["url"] = f"https://www.amazon.com/dp/{asin}"

        price_whole = re.search(r'<span class="a-price-whole">(\d[\d,]*)', block)
        price_frac = re.search(r'<span class="a-price-fraction">(\d+)', block)
        if price_whole:
            price_str = price_whole.group(1).replace(",", "")
            frac = price_frac.group(1) if price_frac else "00"
            listing["price"] = float(f"{price_str}.{frac}")
            listing["price_text"] = f"${listing['price']:.2f}"

        rating_match = re.search(r'(\d\.?\d?) out of 5 stars', block)
        if rating_match:
            listing["rating"] = float(rating_match.group(1))

        if "a-icon-prime" in block or "Prime" in block:
            listing["prime"] = True

        if "FREE delivery" in block or "free shipping" in block.lower() or listing.get("prime"):
            listing["shipping"] = "Free"
            listing["shipping_cost"] = 0.0
        else:
            ship_match = re.search(r'\$(\d+\.?\d*)\s*(?:delivery|shipping)', block, re.IGNORECASE)
            if ship_match:
                listing["shipping_cost"] = float(ship_match.group(1))
                listing["shipping"] = f"+${ship_match.group(1)} shipping"
            else:
                listing["shipping_cost"] = 0.0
                listing["shipping"] = "Unknown"

        if listing.get("title"):
            listings.append(listing)

    return listings


@tool
@retry()
def amazon_search(
    query: str,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort: str = "relevance",
    max_results: int = 20,
) -> str:
    """Search Amazon and return parsed product listings.

    WHEN TO USE: When searching for products on Amazon specifically.
    WHEN NOT TO USE: When you want to search multiple platforms at once (use cross_platform_search).

    Args:
        query: Search terms (e.g. "RTX 3060", "mechanical keyboard"). Must be non-empty.
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        sort: Sort order. One of: "relevance", "price_low", "price_high", "avg_review", "newest".
        max_results: Maximum listings to return. Range: 1-100.

    Output format:
        {"status": "success", "data": {"query": "...", "count": N, "listings": [...]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.amazon.com/s?k={encoded}"

    sort_map = {
        "relevance": "",
        "price_low": "&s=price-asc-rank",
        "price_high": "&s=price-desc-rank",
        "avg_review": "&s=review-rank",
        "newest": "&s=date-desc-rank",
    }
    url += sort_map.get(sort, "")

    if min_price is not None or max_price is not None:
        lo = int(min_price * 100) if min_price is not None else ""
        hi = int(max_price * 100) if max_price is not None else ""
        url += f"&rh=p_36%3A{lo}-{hi}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return tool_result(error=str(e))

    listings = _parse_amazon_listings(html)[:max_results]

    for listing in listings:
        model = _extract_gpu_model(listing.get("title", ""))
        if model:
            listing["gpu_model"] = model

    return tool_result(data={"query": query, "count": len(listings), "listings": listings})


# ── Craigslist Operations ─────────────────────────────────────────────────────

CRAIGSLIST_DENVER_AREA = {
    "denver":           "https://denver.craigslist.org",
    "boulder":          "https://boulder.craigslist.org",
    "colorado springs": "https://cosprings.craigslist.org",
    "fort collins":     "https://fortcollins.craigslist.org",
    "pueblo":           "https://pueblo.craigslist.org",
}

CRAIGSLIST_SHIPPING_CITIES = {
    "los angeles":  "https://losangeles.craigslist.org",
    "san francisco":"https://sfbay.craigslist.org",
    "san diego":    "https://sandiego.craigslist.org",
    "seattle":      "https://seattle.craigslist.org",
    "portland":     "https://portland.craigslist.org",
    "phoenix":      "https://phoenix.craigslist.org",
    "dallas":       "https://dallas.craigslist.org",
    "houston":      "https://houston.craigslist.org",
    "austin":       "https://austin.craigslist.org",
    "chicago":      "https://chicago.craigslist.org",
    "new york":     "https://newyork.craigslist.org",
    "atlanta":      "https://atlanta.craigslist.org",
    "miami":        "https://miami.craigslist.org",
    "minneapolis":  "https://minneapolis.craigslist.org",
    "detroit":      "https://detroit.craigslist.org",
    "boston":        "https://boston.craigslist.org",
    "philadelphia": "https://philadelphia.craigslist.org",
    "washington dc":"https://washingtondc.craigslist.org",
    "las vegas":    "https://lasvegas.craigslist.org",
    "salt lake city":"https://saltlakecity.craigslist.org",
}


def _parse_craigslist_listings(html: str, city: str, is_local: bool) -> list[dict]:
    """Extract listing data from Craigslist search results HTML."""
    listings = []

    new_items = re.findall(
        r'<li class="cl-static-search-result"[^>]*>(.*?)</li>',
        html, re.DOTALL,
    )

    if new_items:
        for block in new_items:
            listing: dict = {"city": city}
            listing["fulfillment"] = "pickup" if is_local else "shipping_required"

            link = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if link:
                listing["url"] = link.group(1)
                listing["title"] = re.sub(r"<[^>]+>", "", link.group(2)).strip()

            price_match = re.search(r'<div class="price">\s*\$?([\d,]+)', block)
            if price_match:
                listing["price"] = float(price_match.group(1).replace(",", ""))
                listing["price_text"] = f"${listing['price']:.0f}"

            if listing.get("title") and listing.get("url"):
                listings.append(listing)
    else:
        legacy_items = re.findall(
            r'<li class="result-row"[^>]*>(.*?)</li>',
            html, re.DOTALL,
        )
        for block in legacy_items:
            listing = {"city": city}
            listing["fulfillment"] = "pickup" if is_local else "shipping_required"

            link = re.search(r'href="([^"]+)"[^>]*class="result-title[^"]*">(.*?)</a>', block, re.DOTALL)
            if link:
                listing["url"] = link.group(1)
                listing["title"] = re.sub(r"<[^>]+>", "", link.group(2)).strip()

            price_match = re.search(r'<span class="result-price">\$?([\d,]+)', block)
            if price_match:
                listing["price"] = float(price_match.group(1).replace(",", ""))
                listing["price_text"] = f"${listing['price']:.0f}"

            if listing.get("title") and listing.get("url"):
                listings.append(listing)

    return listings


def _craigslist_search_city(
    base_url: str,
    query: str,
    city: str,
    is_local: bool,
    category: str = "sss",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    max_results: int = 25,
) -> list[dict]:
    """Search a single Craigslist city and return parsed listings."""
    encoded = urllib.parse.quote_plus(query)
    url = f"{base_url}/search/{category}?query={encoded}"
    if min_price is not None:
        url += f"&min_price={min_price}"
    if max_price is not None:
        url += f"&max_price={max_price}"
    if not is_local:
        url += "&shipping=1"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    return _parse_craigslist_listings(html, city, is_local)[:max_results]


@tool
@retry()
def craigslist_search(
    query: str,
    city: str = "denver",
    category: str = "sss",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    max_results: int = 25,
) -> str:
    """Search Craigslist in a specific city.

    WHEN TO USE: When you need Craigslist results from one specific city.
    WHEN NOT TO USE: When you need results from multiple cities (use craigslist_multi_search).

    Cities within ~100mi of Denver (pickup available): denver, boulder,
    colorado springs, fort collins, pueblo.

    Cities outside that radius require shipping. Available: los angeles,
    san francisco, san diego, seattle, portland, phoenix, dallas, houston,
    austin, chicago, new york, atlanta, miami, minneapolis, detroit, boston,
    philadelphia, washington dc, las vegas, salt lake city.

    Args:
        query: Search terms. Must be non-empty.
        city: City name (see above). Defaults to denver.
        category: Craigslist category code. "sss" = for sale, "cta" = cars+trucks,
                  "sys" = computers, "ele" = electronics.
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        max_results: Maximum listings to return. Range: 1-100.

    Output format:
        {"status": "success", "data": {"query": "...", "city": "...", "count": N, "listings": [...]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    city_lower = city.lower().strip()

    if city_lower in CRAIGSLIST_DENVER_AREA:
        base_url = CRAIGSLIST_DENVER_AREA[city_lower]
        is_local = True
    elif city_lower in CRAIGSLIST_SHIPPING_CITIES:
        base_url = CRAIGSLIST_SHIPPING_CITIES[city_lower]
        is_local = False
    else:
        all_cities = sorted(list(CRAIGSLIST_DENVER_AREA.keys()) + list(CRAIGSLIST_SHIPPING_CITIES.keys()))
        return tool_result(error=f"Unknown city '{city}'. Use one of: {', '.join(all_cities)}")

    listings = _craigslist_search_city(
        base_url, query, city_lower, is_local,
        category=category, min_price=min_price, max_price=max_price,
        max_results=max_results,
    )

    for listing in listings:
        model = _extract_gpu_model(listing.get("title", ""))
        if model:
            listing["gpu_model"] = model

    return tool_result(data={"query": query, "city": city_lower, "count": len(listings), "listings": listings})


@tool
@retry()
def craigslist_multi_search(
    query: str,
    scope: str = "local",
    category: str = "sss",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    max_results_per_city: int = 10,
) -> str:
    """Search Craigslist across multiple cities with rate-limiting.

    WHEN TO USE: When you need Craigslist results from multiple cities at once.
    WHEN NOT TO USE: When you only need results from one city (use craigslist_search).

    PIPELINE STEPS (executed internally — you call this tool ONCE):
        1. Build city list based on scope ("local", "shipping", or "all")
        2. For each city: fetch search results page, parse listings
        3. Rate-limit delay (1.5-3 seconds) between city requests
        4. Enrich listings with GPU model extraction
        5. Sort by price ascending, aggregate with per-city counts

    CONSTRAINTS:
        - "local" scope: 5 cities (Denver area), ~10-15 seconds
        - "shipping" scope: 20 cities, ~40-60 seconds
        - "all" scope: 25 cities, ~50-75 seconds

    Args:
        query: Search terms. Must be non-empty.
        scope: Which cities to search. One of: "local", "shipping", "all".
        category: Craigslist category code. "sss" = for sale, "sys" = computers, "ele" = electronics, "cta" = cars+trucks.
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        max_results_per_city: Maximum listings per city. Range: 1-50.

    Output format:
        {"status": "success", "data": {"total_listings": N, "cities_searched": [...], "listings": [...]}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    cities_to_search: list[tuple[str, str, bool]] = []

    if scope in ("local", "all"):
        for city_name, base_url in CRAIGSLIST_DENVER_AREA.items():
            cities_to_search.append((city_name, base_url, True))
    if scope in ("shipping", "all"):
        for city_name, base_url in CRAIGSLIST_SHIPPING_CITIES.items():
            cities_to_search.append((city_name, base_url, False))

    if not cities_to_search:
        return tool_result(error=f"Invalid scope '{scope}'. Use 'local', 'shipping', or 'all'.")

    all_listings = []
    cities_searched = []
    cities_failed = []

    for i, (city_name, base_url, is_local) in enumerate(cities_to_search):
        results = _craigslist_search_city(
            base_url, query, city_name, is_local,
            category=category, min_price=min_price, max_price=max_price,
            max_results=max_results_per_city,
        )

        if results:
            for listing in results:
                model = _extract_gpu_model(listing.get("title", ""))
                if model:
                    listing["gpu_model"] = model
            all_listings.extend(results)
            cities_searched.append(f"{city_name} ({len(results)} results)")
        else:
            cities_failed.append(city_name)

        if i < len(cities_to_search) - 1:
            time.sleep(random.uniform(1.5, 3.0))

    all_listings.sort(key=lambda x: (x.get("price") is None, x.get("price", 999999)))

    return tool_result(data={
        "total_listings": len(all_listings),
        "cities_searched": cities_searched,
        "cities_with_no_results": cities_failed,
        "listings": all_listings,
    })


# ── Cross-Platform Flow Tools ─────────────────────────────────────────────────

@tool
@retry()
def cross_platform_search(
    query: str,
    platforms: str = "all",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: str = "",
    max_results_per_platform: int = 15,
) -> str:
    """Search across eBay, Amazon, and Craigslist in a single call.

    WHEN TO USE: When you need to compare prices across multiple marketplaces.
    WHEN NOT TO USE: When you only need results from one platform (use the specific platform tool).

    PIPELINE STEPS (executed internally — you call this tool ONCE):
        1. Parse platform list from 'platforms' arg
        2. For each platform, call: ebay_search / amazon_search / craigslist_multi_search
        3. Rate-limit delay (2-4 seconds) between each platform call
        4. Aggregate all results, tag each with source platform
        5. Return combined results

    CONSTRAINTS:
        - Total execution time: 10-30 seconds depending on platforms selected
        - Rate-limited: 2-4 second delay between platform requests
        - Craigslist sub-call searches multiple cities internally (additional delays)

    Args:
        query: Search terms. Must be non-empty.
        platforms: Comma-separated list or "all". Options: "ebay", "amazon", "craigslist".
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        condition: Condition filter for eBay only. One of: "new", "used", "refurbished", "parts", or "" to skip.
        max_results_per_platform: Maximum listings per platform. Range: 1-50.

    Output format:
        {"status": "success", "data": {"query": "...", "platforms_searched": [...], "total_listings": N, "results": {"ebay": [...], ...}}, "error": ""}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    platform_list = [p.strip().lower() for p in platforms.split(",")]
    if "all" in platform_list:
        platform_list = ["ebay", "amazon", "craigslist"]

    aggregated: dict = {
        "query": query,
        "platforms_searched": [],
        "total_listings": 0,
        "results": {},
    }

    for i, platform in enumerate(platform_list):
        if platform == "ebay":
            try:
                raw = ebay_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "condition": condition,
                    "max_results": max_results_per_platform,
                })
                parsed = json.loads(raw)
                listings = parsed.get("data", {}).get("listings", []) if parsed.get("status") == "success" else []
                for listing in listings:
                    listing["platform"] = "ebay"
                    listing["fulfillment"] = "shipping"
                    model = _extract_gpu_model(listing.get("title", ""))
                    if model:
                        listing["gpu_model"] = model
                aggregated["results"]["ebay"] = listings
                aggregated["platforms_searched"].append(f"ebay ({len(listings)} results)")
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["ebay"] = [{"error": str(e)}]

        elif platform == "amazon":
            try:
                raw = amazon_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "max_results": max_results_per_platform,
                })
                parsed = json.loads(raw)
                listings = parsed.get("data", {}).get("listings", []) if parsed.get("status") == "success" else []
                for listing in listings:
                    listing["platform"] = "amazon"
                    listing["fulfillment"] = "shipping"
                aggregated["results"]["amazon"] = listings
                aggregated["platforms_searched"].append(f"amazon ({len(listings)} results)")
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["amazon"] = [{"error": str(e)}]

        elif platform == "craigslist":
            try:
                raw = craigslist_multi_search.invoke({
                    "query": query,
                    "scope": "all",
                    "min_price": int(min_price) if min_price is not None else None,
                    "max_price": int(max_price) if max_price is not None else None,
                    "max_results_per_city": max(3, max_results_per_platform // 5),
                })
                parsed = json.loads(raw)
                cl_data = parsed.get("data", {}) if parsed.get("status") == "success" else {}
                listings = cl_data.get("listings", [])
                for listing in listings:
                    listing["platform"] = "craigslist"
                aggregated["results"]["craigslist"] = listings
                aggregated["platforms_searched"].append(
                    f"craigslist ({len(listings)} results across {len(cl_data.get('cities_searched', []))} cities)"
                )
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["craigslist"] = [{"error": str(e)}]

        if i < len(platform_list) - 1:
            time.sleep(random.uniform(2.0, 4.0))

    return tool_result(data=aggregated)


@tool
@retry()
def deal_finder(
    query: str,
    platforms: str = "all",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: str = "used",
    threshold_pct: float = 20.0,
) -> str:
    """Find deals by comparing prices across platforms against median market price.

    WHEN TO USE: When you want to find underpriced listings across multiple marketplaces.
    WHEN NOT TO USE: When you just need search results without price analysis (use cross_platform_search).

    PIPELINE STEPS (executed internally — you call this tool ONCE):
        1. For each platform, collect listings:
           - eBay: 3-page deep scan via ebay_deep_scan
           - Amazon: standard search via amazon_search
           - Craigslist: multi-city search via craigslist_multi_search
        2. Rate-limit delay (2-4 seconds) between platform calls
        3. Group all listings by extracted product model name
        4. For each group with >=3 listings: compute median price
        5. Flag listings priced >= threshold_pct below their group median
        6. Sort deals by savings percentage (best first)

    CONSTRAINTS:
        - Total execution time: 30-90 seconds (deep scan + multi-city)
        - Requires >=3 listings per model for reliable comparison
        - Models with <3 listings are noted but not analyzed

    Args:
        query: Search terms. Must be non-empty.
        platforms: Comma-separated list or "all". Options: "ebay", "amazon", "craigslist".
        min_price: Minimum price in USD. None to skip filter.
        max_price: Maximum price in USD. None to skip filter.
        condition: Condition filter for eBay. One of: "new", "used", "refurbished", "parts".
        threshold_pct: Minimum percentage below median to flag as a deal. Default: 20.0.

    Output format:
        {"status": "success", "data": {"query": "...", "total_listings_analyzed": N, "group_statistics": {...}, "deals_found": N, "deals": [...]}, "error": ""}
    """
    import statistics

    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    platform_list = [p.strip().lower() for p in platforms.split(",")]
    if "all" in platform_list:
        platform_list = ["ebay", "amazon", "craigslist"]

    all_listings: list[dict] = []
    platforms_searched = []

    for i, platform in enumerate(platform_list):
        if platform == "ebay":
            try:
                raw = ebay_deep_scan.invoke({
                    "query": query,
                    "condition": condition,
                    "min_price": min_price,
                    "max_price": max_price,
                    "pages": 3,
                    "max_results": 100,
                })
                parsed = json.loads(raw)
                listings = parsed.get("data", {}).get("listings", []) if parsed.get("status") == "success" else []
                for lst in listings:
                    lst["platform"] = "ebay"
                    lst["fulfillment"] = "shipping"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0) + lst.get("shipping_cost", 0)
                all_listings.extend(listings)
                platforms_searched.append(f"ebay ({len(listings)} listings, 3-page deep scan)")
            except Exception as e:
                platforms_searched.append(f"ebay (error: {e})")

        elif platform == "amazon":
            try:
                raw = amazon_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "max_results": 30,
                })
                parsed = json.loads(raw)
                listings = parsed.get("data", {}).get("listings", []) if parsed.get("status") == "success" else []
                for lst in listings:
                    lst["platform"] = "amazon"
                    lst["fulfillment"] = "shipping"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0) + lst.get("shipping_cost", 0)
                    if "model" not in lst and "gpu_model" in lst:
                        lst["model"] = lst["gpu_model"]
                    elif "model" not in lst:
                        lst["model"] = _extract_gpu_model(lst.get("title", ""))
                all_listings.extend(listings)
                platforms_searched.append(f"amazon ({len(listings)} listings)")
            except Exception as e:
                platforms_searched.append(f"amazon (error: {e})")

        elif platform == "craigslist":
            try:
                raw = craigslist_multi_search.invoke({
                    "query": query,
                    "scope": "all",
                    "min_price": int(min_price) if min_price is not None else None,
                    "max_price": int(max_price) if max_price is not None else None,
                    "max_results_per_city": 5,
                })
                parsed = json.loads(raw)
                cl_data = parsed.get("data", {}) if parsed.get("status") == "success" else {}
                listings = cl_data.get("listings", [])
                for lst in listings:
                    lst["platform"] = "craigslist"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0)
                    if "model" not in lst and "gpu_model" in lst:
                        lst["model"] = lst["gpu_model"]
                    elif "model" not in lst:
                        lst["model"] = _extract_gpu_model(lst.get("title", ""))
                all_listings.extend(listings)
                n_cities = len(cl_data.get("cities_searched", []))
                platforms_searched.append(f"craigslist ({len(listings)} listings across {n_cities} cities)")
            except Exception as e:
                platforms_searched.append(f"craigslist (error: {e})")

        if i < len(platform_list) - 1:
            time.sleep(random.uniform(2.0, 4.0))

    # Group by model
    groups: dict[str, list[dict]] = {}
    ungrouped = []
    for lst in all_listings:
        model = lst.get("model", "")
        if model:
            groups.setdefault(model, []).append(lst)
        else:
            ungrouped.append(lst)

    # Compute medians and find deals
    deals = []
    group_stats = {}

    for model, items in groups.items():
        prices = [x["total_cost"] for x in items if x.get("total_cost", 0) > 0]
        if len(prices) < 3:
            group_stats[model] = {
                "count": len(items),
                "note": "Too few listings for reliable comparison (need >=3)",
            }
            continue

        median_price = statistics.median(prices)
        group_stats[model] = {
            "count": len(items),
            "median_price": round(median_price, 2),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
        }

        threshold = median_price * (1 - threshold_pct / 100)
        for item in items:
            total = item.get("total_cost", 0)
            if total > 0 and total <= threshold:
                pct_below = round((1 - total / median_price) * 100, 1)
                savings = round(median_price - total, 2)
                deals.append({
                    "model": model,
                    "title": item.get("title", ""),
                    "total_cost": total,
                    "median_price": round(median_price, 2),
                    "pct_below_median": pct_below,
                    "savings": savings,
                    "platform": item.get("platform", ""),
                    "fulfillment": item.get("fulfillment", ""),
                    "url": item.get("url", ""),
                })

    deals.sort(key=lambda x: x["pct_below_median"], reverse=True)

    return tool_result(data={
        "query": query,
        "platforms_searched": platforms_searched,
        "total_listings_analyzed": len(all_listings),
        "models_found": len(groups),
        "ungrouped_listings": len(ungrouped),
        "group_statistics": group_stats,
        "deals_found": len(deals),
        "threshold": f">={threshold_pct}% below median",
        "deals": deals,
    })


# ── Enrichment Pipeline ──────────────────────────────────────────────────────

@tool
@retry()
def enrichment_pipeline(
    data: str,
    goal: str,
    max_iterations: int = 5,
    eval_model: str = "qwen3:4b",
) -> str:
    """Iteratively enrich data by adding new analysis dimensions using an LLM eval loop.

    WHEN TO USE: When you have raw data that needs multi-pass enrichment (scoring, categorizing, flagging).
    WHEN NOT TO USE: When you need a simple one-shot analysis (just ask the main LLM directly).

    PIPELINE STEPS (executed internally — you call this tool ONCE):
        1. Initialize small eval model (default: qwen3:4b via Ollama)
        2. Send current data + goal to eval model
        3. Eval model responds with: {"action": "enrich", "dimension": "...", "enriched_data": {...}}
           OR: {"action": "done", "reasoning": "..."}
        4. If "enrich": merge enriched_data, repeat from step 2
        5. If "done" OR max_iterations reached OR 2 consecutive failures: stop
        6. Return iteration log + final enriched data

    CONSTRAINTS:
        - Requires Ollama running locally at http://localhost:11434
        - Data is truncated to 4000 chars for eval model context
        - Max 5 iterations by default (configurable)
        - Stops on 2 consecutive eval model failures

    Args:
        data: Input data to enrich. JSON string from a prior tool call, or raw text. Must be non-empty.
        goal: Natural language description of enrichment dimensions to add.
        max_iterations: Maximum loop iterations. Range: 1-10. Default: 5.
        eval_model: Ollama model name for evaluation. Default: "qwen3:4b".

    Output format:
        {"status": "success", "data": {"iterations_used": N, "exit_reason": "llm_done"|"max_iterations"|"consecutive_failures", "iteration_log": [...], "enriched_data": {...}}, "error": ""}
    """
    if not data or not data.strip():
        return tool_result(error="Empty data input. Provide data to enrich.")

    try:
        from config import OLLAMA_NUM_CTX
        eval_llm = ChatOllama(
            model=eval_model,
            temperature=0,
            base_url="http://localhost:11434",
            num_ctx=OLLAMA_NUM_CTX,
        )
    except Exception as e:
        return tool_result(error=f"Failed to initialize eval model '{eval_model}': {e}. Run: ollama pull {eval_model}")

    system_prompt = """You are a data enrichment engine. Your job is to iteratively add new dimensions/considerations to data until the goal is fully satisfied.

Respond ONLY with valid JSON (no markdown fences, no explanation outside JSON).

If there are more dimensions to add, respond with:
{"action": "enrich", "dimension": "short_name", "description": "what you added and why", "enriched_data": <the full data with the new dimension merged in>}

If the goal is fully satisfied, respond with:
{"action": "done", "reasoning": "why all requested dimensions are complete"}"""

    current_data = data
    iteration_log = []
    consecutive_failures = 0

    for iteration in range(1, max_iterations + 1):
        display_data = current_data
        if len(current_data) > 4000:
            display_data = current_data[:4000]
            iteration_log.append({
                "iteration": iteration,
                "warning": f"Data truncated from {len(current_data)} to 4000 chars for eval model",
            })

        log_summary = "None yet" if not iteration_log else json.dumps(
            [e for e in iteration_log if "dimension" in e], indent=2
        )

        user_prompt = f"""GOAL: {goal}

CURRENT DATA:
{display_data}

PREVIOUS ITERATIONS:
{log_summary}

Iteration {iteration} of {max_iterations}. Add the next enrichment dimension, or signal done."""

        response_text = ""
        try:
            result = eval_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            response_text = result.content.strip()

            fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", response_text, re.DOTALL)
            if fence_match:
                response_text = fence_match.group(1).strip()

            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": "Malformed JSON from eval model",
                "raw_response": response_text[:200],
            })
            if consecutive_failures >= 2:
                break
            continue
        except Exception as e:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": f"Eval model call failed: {e}",
            })
            if consecutive_failures >= 2:
                break
            continue

        consecutive_failures = 0
        action = parsed.get("action", "")

        if action == "done":
            iteration_log.append({
                "iteration": iteration,
                "action": "done",
                "reasoning": parsed.get("reasoning", ""),
            })
            break

        elif action == "enrich":
            enriched = parsed.get("enriched_data")
            if enriched is not None:
                current_data = json.dumps(enriched, indent=2) if not isinstance(enriched, str) else enriched
            iteration_log.append({
                "iteration": iteration,
                "action": "enrich",
                "dimension": parsed.get("dimension", "unknown"),
                "description": parsed.get("description", ""),
            })

        else:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": f"Unknown action '{action}' from eval model",
            })
            if consecutive_failures >= 2:
                break

    if consecutive_failures >= 2:
        exit_reason = "consecutive_failures"
    elif iteration_log and iteration_log[-1].get("action") == "done":
        exit_reason = "llm_done"
    else:
        exit_reason = "max_iterations"

    try:
        final_data = json.loads(current_data)
    except (json.JSONDecodeError, TypeError):
        final_data = current_data

    return tool_result(data={
        "iterations_used": len([e for e in iteration_log if e.get("action") in ("enrich", "done") or "error" in e]),
        "max_iterations": max_iterations,
        "exit_reason": exit_reason,
        "iteration_log": iteration_log,
        "enriched_data": final_data,
    })


# ── Registry ─────────────────────────────────────────────────────────────────

ECOMMERCE_TOOLS = [
    ebay_search,
    ebay_sold_search,
    ebay_deep_scan,
    amazon_search,
    craigslist_search,
    craigslist_multi_search,
]

# Flow tools call ecommerce tools internally — owned by dispatcher, not ecommerce agent
FLOW_TOOLS = [
    cross_platform_search,
    deal_finder,
    enrichment_pipeline,
]
