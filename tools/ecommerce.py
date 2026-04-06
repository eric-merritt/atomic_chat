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


def _validate_query(query: str) -> str | None:
    """Return error string if query is invalid, None if ok."""
    if not query.strip():
        return "query must be a non-empty string"
    return None


def _ebay_url(query: str, sort: str = "best_match", min_price=None, max_price=None,
              condition: str = "", sold: bool = False, page: int = 1) -> str:
    """Build an eBay search URL."""
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
    if sold:
        url += "&LH_Complete=1&LH_Sold=1"
    else:
        url += "&LH_BIN=1"
    url += "&rt=nc"
    if page > 1:
        url += f"&_pgn={page}"
    return url


_EBAY_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}


def _fetch_html(url: str, headers: dict = None) -> str:
    """Fetch a URL and return decoded HTML. Raises on failure."""
    req = urllib.request.Request(url, headers=headers or _EBAY_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


class _EbaySearchHandler(BaseTool):
    description = 'Search eBay listings by keyword with optional filters.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms.'},
            'sort': {'type': 'string', 'description': 'Sort: best_match, ending_soonest, newly_listed, price_low, price_high.'},
            'min_price': {'type': 'number', 'description': 'Minimum price USD.'},
            'max_price': {'type': 'number', 'description': 'Maximum price USD.'},
            'condition': {'type': 'string', 'description': 'new, used, refurbished, or parts.'},
            'sold': {'type': 'boolean', 'description': 'Search completed/sold listings instead of active. Default: false.'},
            'pages': {'type': 'integer', 'description': 'Pages to scrape (1-10). Default: 1.'},
            'max_results': {'type': 'integer', 'description': 'Max listings to return. Default: 20.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        err = _validate_query(query)
        if err:
            return tool_result(error=err)

        sort = p.get('sort', 'best_match')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        condition = p.get('condition', '')
        sold = p.get('sold', False)
        pages = max(1, min(p.get('pages', 1), 10))
        max_results = p.get('max_results', 20)

        seen_urls = set()
        all_listings = []

        for page_num in range(1, pages + 1):
            url = _ebay_url(query, sort, min_price, max_price, condition, sold, page_num)
            try:
                html = _fetch_html(url)
            except Exception:
                if page_num < pages:
                    time.sleep(random.uniform(3.0, 6.0))
                continue

            for listing in _parse_ebay_listings(html):
                item_url = listing.get("url", "")
                if not item_url or item_url in seen_urls:
                    continue
                seen_urls.add(item_url)
                if sold:
                    listing["sold"] = True
                all_listings.append(listing)

            if page_num < pages:
                time.sleep(random.uniform(3.0, 6.0))

        all_listings = all_listings[:max_results]
        return tool_result(data={"query": query, "count": len(all_listings), "listings": all_listings})


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


class _AmazonSearchHandler(BaseTool):
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


class _CraigslistSearchHandler(BaseTool):
    description = 'Search Craigslist in one city or across multiple cities.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search terms.'},
            'city': {'type': 'string', 'description': 'Single city name. Ignored if scope is set.'},
            'scope': {'type': 'string', 'description': 'Search multiple cities: "local" (Denver area), "shipping" (20 cities), or "all". Overrides city.'},
            'category': {'type': 'string', 'description': 'Category: sss (for sale), cta (cars), sys (computers), ele (electronics). Default: sss.'},
            'min_price': {'type': 'integer', 'description': 'Minimum price USD.'},
            'max_price': {'type': 'integer', 'description': 'Maximum price USD.'},
            'max_results': {'type': 'integer', 'description': 'Max listings per city. Default: 25.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        err = _validate_query(query)
        if err:
            return tool_result(error=err)

        scope = p.get('scope')
        city = p.get('city', 'denver')
        category = p.get('category', 'sss')
        min_price = p.get('min_price')
        max_price = p.get('max_price')
        max_results = p.get('max_results', 25)

        if scope:
            cities = []
            if scope in ("local", "all"):
                cities += [(n, u, True) for n, u in CRAIGSLIST_DENVER_AREA.items()]
            if scope in ("shipping", "all"):
                cities += [(n, u, False) for n, u in CRAIGSLIST_SHIPPING_CITIES.items()]
            if not cities:
                return tool_result(error=f"Invalid scope '{scope}'. Use 'local', 'shipping', or 'all'.")
        else:
            city_lower = city.lower().strip()
            if city_lower in CRAIGSLIST_DENVER_AREA:
                cities = [(city_lower, CRAIGSLIST_DENVER_AREA[city_lower], True)]
            elif city_lower in CRAIGSLIST_SHIPPING_CITIES:
                cities = [(city_lower, CRAIGSLIST_SHIPPING_CITIES[city_lower], False)]
            else:
                all_cities = sorted(list(CRAIGSLIST_DENVER_AREA) + list(CRAIGSLIST_SHIPPING_CITIES))
                return tool_result(error=f"Unknown city '{city}'. Use one of: {', '.join(all_cities)}")

        all_listings = []
        for i, (name, base_url, is_local) in enumerate(cities):
            results = _craigslist_search_city(
                base_url, query, name, is_local,
                category=category, min_price=min_price, max_price=max_price,
                max_results=max_results,
            )
            all_listings.extend(results)
            if i < len(cities) - 1:
                time.sleep(random.uniform(1.5, 3.0))

        return tool_result(data={"query": query, "count": len(all_listings), "listings": all_listings})


# ── Unified Search Dispatcher ────────────────────────────────────────────────

_EC_HANDLERS = {
    'ebay': _EbaySearchHandler,
    'amazon': _AmazonSearchHandler,
    'cl': _CraigslistSearchHandler,
}


@register_tool('ec_search')
class EcommerceSearchTool(BaseTool):
    description = (
        'Search ecommerce platforms for product listings. '
        'platform: ebay, amazon, or cl (Craigslist). '
        'Pass query and platform-specific params (sort, condition, sold, city, scope, etc.).'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'platform': {
                'type': 'string',
                'enum': ['ebay', 'amazon', 'cl'],
                'description': 'Platform to search.',
            },
            'query': {'type': 'string', 'description': 'Search terms.'},
            'sort': {'type': 'string', 'description': 'Sort order (platform-specific).'},
            'min_price': {'type': 'number', 'description': 'Minimum price USD.'},
            'max_price': {'type': 'number', 'description': 'Maximum price USD.'},
            'condition': {'type': 'string', 'description': 'Item condition (ebay): new, used, refurbished, parts.'},
            'sold': {'type': 'boolean', 'description': 'Search sold listings (ebay only). Default: false.'},
            'pages': {'type': 'integer', 'description': 'Pages to scrape (ebay, 1-10). Default: 1.'},
            'max_results': {'type': 'integer', 'description': 'Max listings to return. Default: 20.'},
            'city': {'type': 'string', 'description': 'City name (cl only). Ignored if scope is set.'},
            'scope': {'type': 'string', 'description': 'Multi-city scope (cl only): local, shipping, or all.'},
            'category': {'type': 'string', 'description': 'Craigslist category code (cl only): sss, cta, sys, ele.'},
        },
        'required': ['platform', 'query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        platform = p.pop('platform', 'ebay')

        handler_cls = _EC_HANDLERS.get(platform)
        if not handler_cls:
            return tool_result(error=f"Invalid platform '{platform}'. Use: ebay, amazon, cl")

        return handler_cls().call(json5.dumps(p), **kwargs)


# ── Enrichment Pipeline ──────────────────────────────────────────────────────

@register_tool('ec_enrich')
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
