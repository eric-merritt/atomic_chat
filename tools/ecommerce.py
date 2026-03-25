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

import json5
from qwen_agent.tools.base import BaseTool, register_tool

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


@register_tool('ebay_search')
class EbaySearchTool(BaseTool):
    description = 'Search eBay Buy It Now listings and return parsed results.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms (e.g. "RTX 3060"). Must be non-empty.'},
            'sort': {'type': 'string', 'description': 'Sort order: best_match, ending_soonest, newly_listed, price_low, price_high.'},
            'min_price': {'type': 'number', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'number', 'description': 'Maximum price in USD. Omit to skip.'},
            'condition': {'type': 'string', 'description': 'Item condition: new, used, refurbished, parts, or "" to skip.'},
            'max_results': {'type': 'integer', 'description': 'Maximum listings to return. Range: 1-100.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        sort = p.get('sort', 'best_match')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        condition = p.get('condition', '')
        max_results = p.get('max_results', 20)

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


@register_tool('ebay_sold_search')
class EbaySoldSearchTool(BaseTool):
    description = 'Search eBay completed/sold listings to find market prices.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'max_results': {'type': 'integer', 'description': 'Maximum listings to return. Range: 1-100.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        max_results = p.get('max_results', 20)

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


@register_tool('ebay_deep_scan')
class EbayDeepScanTool(BaseTool):
    description = 'Paginated eBay search that compresses results to model + price for bulk analysis.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'condition': {'type': 'string', 'description': 'Filter: new, used, refurbished, parts, or "" to skip.'},
            'min_price': {'type': 'number', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'number', 'description': 'Maximum price in USD. Omit to skip.'},
            'sort': {'type': 'string', 'description': 'Sort order: best_match, ending_soonest, newly_listed, price_low, price_high.'},
            'pages': {'type': 'integer', 'description': 'Number of result pages to scrape. Range: 1-10.'},
            'max_results': {'type': 'integer', 'description': 'Maximum total listings to return. Range: 1-500.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        condition = p.get('condition', 'used')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        sort = p.get('sort', 'best_match')
        pages = p.get('pages', 5)
        max_results = p.get('max_results', 200)

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


@register_tool('amazon_search')
class AmazonSearchTool(BaseTool):
    description = 'Search Amazon and return parsed product listings.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'min_price': {'type': 'number', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'number', 'description': 'Maximum price in USD. Omit to skip.'},
            'sort': {'type': 'string', 'description': 'Sort order: relevance, price_low, price_high, avg_review, newest.'},
            'max_results': {'type': 'integer', 'description': 'Maximum listings to return. Range: 1-100.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        sort = p.get('sort', 'relevance')
        max_results = p.get('max_results', 20)

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


@register_tool('craigslist_search')
class CraigslistSearchTool(BaseTool):
    description = 'Search Craigslist in a specific city.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'city': {'type': 'string', 'description': 'City name. Denver-area (pickup): denver, boulder, colorado springs, fort collins, pueblo. Remote cities require shipping.'},
            'category': {'type': 'string', 'description': 'Craigslist category code: sss=for sale, cta=cars+trucks, sys=computers, ele=electronics.'},
            'min_price': {'type': 'integer', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'integer', 'description': 'Maximum price in USD. Omit to skip.'},
            'max_results': {'type': 'integer', 'description': 'Maximum listings to return. Range: 1-100.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        city = p.get('city', 'denver')
        category = p.get('category', 'sss')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        max_results = p.get('max_results', 25)

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


@register_tool('craigslist_multi_search')
class CraigslistMultiSearchTool(BaseTool):
    description = 'Search Craigslist across multiple cities with rate-limiting.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'scope': {'type': 'string', 'description': 'Which cities to search: local (Denver area), shipping (20 remote cities), or all (25 cities).'},
            'category': {'type': 'string', 'description': 'Craigslist category code: sss=for sale, sys=computers, ele=electronics, cta=cars+trucks.'},
            'min_price': {'type': 'integer', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'integer', 'description': 'Maximum price in USD. Omit to skip.'},
            'max_results_per_city': {'type': 'integer', 'description': 'Maximum listings per city. Range: 1-50.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        scope = p.get('scope', 'local')
        category = p.get('category', 'sss')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        max_results_per_city = p.get('max_results_per_city', 10)

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

@register_tool('cross_platform_search')
class CrossPlatformSearchTool(BaseTool):
    description = 'Search across eBay, Amazon, and Craigslist in a single call.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'platforms': {'type': 'string', 'description': 'Comma-separated list or "all". Options: ebay, amazon, craigslist.'},
            'min_price': {'type': 'number', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'number', 'description': 'Maximum price in USD. Omit to skip.'},
            'condition': {'type': 'string', 'description': 'Condition filter for eBay only: new, used, refurbished, parts, or "".'},
            'max_results_per_platform': {'type': 'integer', 'description': 'Maximum listings per platform. Range: 1-50.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        platforms = p.get('platforms', 'all')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        condition = p.get('condition', '')
        max_results_per_platform = p.get('max_results_per_platform', 15)

        if not query or not query.strip():
            return tool_result(error="query must be a non-empty string")

        platform_list = [pl.strip().lower() for pl in platforms.split(",")]
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
                    raw = EbaySearchTool().call(json5.dumps({
                        "query": query,
                        "min_price": min_price,
                        "max_price": max_price,
                        "condition": condition,
                        "max_results": max_results_per_platform,
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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
                    raw = AmazonSearchTool().call(json5.dumps({
                        "query": query,
                        "min_price": min_price,
                        "max_price": max_price,
                        "max_results": max_results_per_platform,
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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
                    raw = CraigslistMultiSearchTool().call(json5.dumps({
                        "query": query,
                        "scope": "all",
                        "min_price": int(min_price) if min_price is not None else None,
                        "max_price": int(max_price) if max_price is not None else None,
                        "max_results_per_city": max(3, max_results_per_platform // 5),
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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


@register_tool('deal_finder')
class DealFinderTool(BaseTool):
    description = 'Find deals by comparing prices across platforms against median market price.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms. Must be non-empty.'},
            'platforms': {'type': 'string', 'description': 'Comma-separated list or "all". Options: ebay, amazon, craigslist.'},
            'min_price': {'type': 'number', 'description': 'Minimum price in USD. Omit to skip.'},
            'max_price': {'type': 'number', 'description': 'Maximum price in USD. Omit to skip.'},
            'condition': {'type': 'string', 'description': 'Condition filter for eBay: new, used, refurbished, parts.'},
            'threshold_pct': {'type': 'number', 'description': 'Minimum percentage below median to flag as a deal. Default: 20.0.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        import statistics

        p = json5.loads(params)
        query = p.get('query', '')
        platforms = p.get('platforms', 'all')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        condition = p.get('condition', 'used')
        threshold_pct = p.get('threshold_pct', 20.0)

        if not query or not query.strip():
            return tool_result(error="query must be a non-empty string")

        platform_list = [pl.strip().lower() for pl in platforms.split(",")]
        if "all" in platform_list:
            platform_list = ["ebay", "amazon", "craigslist"]

        all_listings: list[dict] = []
        platforms_searched = []

        for i, platform in enumerate(platform_list):
            if platform == "ebay":
                try:
                    raw = EbayDeepScanTool().call(json5.dumps({
                        "query": query,
                        "condition": condition,
                        "min_price": min_price,
                        "max_price": max_price,
                        "pages": 3,
                        "max_results": 100,
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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
                    raw = AmazonSearchTool().call(json5.dumps({
                        "query": query,
                        "min_price": min_price,
                        "max_price": max_price,
                        "max_results": 30,
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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
                    raw = CraigslistMultiSearchTool().call(json5.dumps({
                        "query": query,
                        "scope": "all",
                        "min_price": int(min_price) if min_price is not None else None,
                        "max_price": int(max_price) if max_price is not None else None,
                        "max_results_per_city": 5,
                    }))
                    parsed = raw if isinstance(raw, dict) else json.loads(raw)
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

@register_tool('enrichment_pipeline')
class EnrichmentPipelineTool(BaseTool):
    description = 'Iteratively enrich data by adding new analysis dimensions using an LLM eval loop.'
    parameters = {
        'type': 'object',
        'properties': {
            'data': {'type': 'string', 'description': 'Input data to enrich. JSON string from a prior tool call, or raw text. Must be non-empty.'},
            'goal': {'type': 'string', 'description': 'Natural language description of enrichment dimensions to add.'},
            'max_iterations': {'type': 'integer', 'description': 'Maximum loop iterations. Range: 1-10. Default: 5.'},
            'eval_model': {'type': 'string', 'description': 'Ollama model name for evaluation. Default: qwen3:4b.'},
        },
        'required': ['data', 'goal'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        data = p.get('data', '')
        goal = p.get('goal', '')
        max_iterations = p.get('max_iterations', 5)
        eval_model = p.get('eval_model', 'qwen3:4b')

        if not data or not data.strip():
            return tool_result(error="Empty data input. Provide data to enrich.")

        try:
            from config import OLLAMA_NUM_CTX
            from qwen_agent.llm import get_chat_model
            eval_llm = get_chat_model({
                'model': f'ollama/{eval_model}',
                'model_server': 'http://localhost:11434/v1',
                'api_key': 'ollama',
                'generate_cfg': {'temperature': 0, 'max_input_tokens': OLLAMA_NUM_CTX},
            })
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
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ]
                response_list = []
                for chunk in eval_llm.chat(messages=messages, stream=False):
                    response_list = chunk
                result_msg = response_list[-1] if response_list else {}
                response_text = result_msg.get('content', '').strip()

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
