"""Web tools: search and fetch URLs."""

import os
import re
import json
import time
import urllib.request
import urllib.parse

import bs4 as beautifulsoup
import requests

from langchain.tools import tool
from tools._output import tool_result


# ── Shared session for cookie persistence across tool calls ──────────────────
_web_session = requests.Session()
_web_session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})


# ── Web Operations ───────────────────────────────────────────────────────────

@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results.

    WHEN TO USE: When you need to search the web for information, answers, or URLs.
    WHEN NOT TO USE: When you already have a specific URL to fetch (use fetch_url instead).

    Args:
        query: Search query string. Must be non-empty.
        num_results: Maximum number of results to return. Range: 1-20.

    Output format:
        {"status": "success", "data": {"abstract": "...", "results": [{"text": "...", "url": "..."}]}, "error": ""}
        {"status": "error", "data": null, "error": "description of failure"}
    """
    if not query or not query.strip():
        return tool_result(error="query must be a non-empty string")

    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return tool_result(error=f"DuckDuckGo search failed: {e}")

    results = []
    abstract = data.get("AbstractText", "")
    abstract_url = data.get("AbstractURL", "")
    for topic in data.get("RelatedTopics", [])[:num_results]:
        if isinstance(topic, dict) and "Text" in topic:
            results.append({"text": topic["Text"], "url": topic.get("FirstURL", "")})

    return tool_result(data={
        "abstract": abstract,
        "abstract_url": abstract_url,
        "results": results,
    })


@tool
def fetch_url(url: str, max_chars: int = 5000, cookies: list[str] | None = None) -> str:
    """Fetch a URL and return its text content with HTML tags stripped.

    WHEN TO USE: When you need to read the text content of a specific webpage.
    WHEN NOT TO USE: When you need raw HTML (use webscrape instead).

    Args:
        url: Full URL to fetch. Must start with http:// or https://.
        max_chars: Maximum characters to return. Range: 100-50000.
        cookies: Optional list of cookie strings in "name=value" format (e.g. ["age_verified=1", "consent=yes"]).

    Output format:
        {"status": "success", "data": {"url": "...", "content": "...", "truncated": false}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    try:
        if cookies:
            for c in cookies:
                if "=" in c:
                    name, _, value = c.partition("=")
                    _web_session.cookies.set(name.strip(), value.strip())
        resp = _web_session.get(url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.text
    except Exception as e:
        return tool_result(error=f"Failed to fetch {url}: {e}")

    if "html" in content_type.lower() or raw.strip().startswith("<"):
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()

    truncated = len(raw) > max_chars
    if truncated:
        raw = raw[:max_chars]

    return tool_result(data={"url": url, "content": raw, "truncated": truncated})


@tool
def webscrape(url: str, cookies: list[str] | None = None) -> str:
    """Fetch a URL and return the raw HTML content.

    WHEN TO USE: When you need the raw HTML of a webpage for parsing with find_all or find_download_link.
    WHEN NOT TO USE: When you need readable text content (use fetch_url instead).

    Args:
        url: Full URL to fetch. Must start with http:// or https://.
        cookies: Optional list of cookie strings in "name=value" format (e.g. ["age_verified=1", "consent=yes"]).

    Output format:
        {"status": "success", "data": {"url": "...", "html": "..."}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    try:
        if cookies:
            for c in cookies:
                if "=" in c:
                    name, _, value = c.partition("=")
                    _web_session.cookies.set(name.strip(), value.strip())
        r = _web_session.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return tool_result(error=f"Failed to fetch {url}: {e}")

    return tool_result(data={"url": url, "html": r.text})


@tool
def find_all(html: str, target: str) -> str:
    """Parse HTML and find all elements matching a tag name.

    WHEN TO USE: When you have raw HTML and need to extract specific elements by tag name.
    WHEN NOT TO USE: When you need download links specifically (use find_download_link instead).

    Args:
        html: Raw HTML string to parse.
        target: HTML tag name to search for (e.g. "a", "img", "div", "video").

    Output format:
        {"status": "success", "data": {"target": "...", "count": N, "elements": ["<tag ...>...</tag>", ...]}, "error": ""}
    """
    if not html or not html.strip():
        return tool_result(error="html must be a non-empty string")
    if not target or not target.strip():
        return tool_result(error="target must be a non-empty HTML tag name")

    try:
        soup = beautifulsoup.BeautifulSoup(html, "html.parser")
        elements = soup.find_all(target)
        element_strings = [str(el) for el in elements]
    except Exception as e:
        return tool_result(error=f"HTML parsing failed: {e}")

    return tool_result(data={
        "target": target,
        "count": len(element_strings),
        "elements": element_strings,
    })


@tool
def find_download_link(html: str = "", url: str = "") -> str:
    """Parse HTML for media download links (video, image, audio sources).

    WHEN TO USE: When you need to find downloadable media URLs in a webpage.
    WHEN NOT TO USE: When you need general link extraction (use find_all with target="a" instead).

    You must provide either html or url (not both empty).
    If url is provided and html is empty, the page will be fetched first.

    Args:
        html: Raw HTML string to parse. If empty, url must be provided.
        url: URL to fetch HTML from. Only used if html is empty.

    Output format:
        {"status": "success", "data": {"links": [{"tag": "video", "src": "..."}, ...]}, "error": ""}
    """
    if not html and not url:
        return tool_result(error="Provide either html or url. Both cannot be empty.")

    if not html and url:
        if not url.startswith(("http://", "https://")):
            return tool_result(error="url must start with http:// or https://")
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "AgentTooling/1.0"})
            r.raise_for_status()
            html = r.text
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

    try:
        soup = beautifulsoup.BeautifulSoup(html, "html.parser")
    except Exception as e:
        return tool_result(error=f"HTML parsing failed: {e}")

    media_tags = ["video", "source", "img", "audio"]
    links = []
    for tag_name in media_tags:
        for el in soup.find_all(tag_name):
            src = el.get("src") or el.get("data-src") or ""
            if src:
                links.append({"tag": tag_name, "src": src})

    return tool_result(data={"links": links})


@tool
def find_allowed_routes(url: str) -> str:
    """Fetch a website's robots.txt and return the allowed crawl paths.

    WHEN TO USE: When you need to check which paths a website allows crawling.
    WHEN NOT TO USE: When you need the actual content of pages (use fetch_url or webscrape).

    Args:
        url: Base URL of the website (e.g. "https://example.com") or direct robots.txt URL.

    Output format:
        {"status": "success", "data": {"url": "...", "allowed": ["/path1", "/path2"]}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    if not url.endswith("robots.txt"):
        url = url.rstrip("/") + "/robots.txt"

    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "AgentTooling/1.0"})
        r.raise_for_status()
        text = r.text
    except Exception as e:
        return tool_result(error=f"Failed to fetch robots.txt: {e}")

    allowed = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("Allow:"):
            path = line.split(":", 1)[1].strip()
            if path:
                allowed.append(path)

    return tool_result(data={"url": url, "allowed": allowed})


# ── Headless Browser ────────────────────────────────────────────────────────

_browser_driver = None


def _get_or_create_browser(geckodriver_path: str = ""):
    """Get or create a headless Firefox browser instance."""
    global _browser_driver
    if _browser_driver is not None:
        return _browser_driver

    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service

    if not geckodriver_path:
        geckodriver_path = os.environ.get(
            "GECKODRIVER_PATH", "/home/ermer/.local/bin/geckodriver"
        )

    options = Options()
    options.add_argument("--headless")
    options.set_preference("general.useragent.override",
                           "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

    service = Service(geckodriver_path)
    _browser_driver = webdriver.Firefox(service=service, options=options)
    _browser_driver.set_page_load_timeout(30)
    return _browser_driver


@tool
def browser_fetch(url: str, wait_seconds: int = 3, cookies: list[str] | None = None) -> str:
    """Fetch a URL using a headless browser that executes JavaScript.

    WHEN TO USE: When a page loads content dynamically via JavaScript (lazy-loaded
    images, SPAs, infinite scroll). This renders the full DOM including JS-generated content.
    WHEN NOT TO USE: For static pages — use fetch_url or webscrape instead (much faster).

    Args:
        url: Full URL to fetch. Must start with http:// or https://.
        wait_seconds: Seconds to wait after page load for JS to execute. Range: 1-30.
        cookies: Optional list of cookie strings in "name=value" format.

    Output format:
        {"status": "success", "data": {"url": "...", "html": "...", "title": "..."}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    wait_seconds = max(1, min(30, wait_seconds))

    try:
        driver = _get_or_create_browser()

        # Set cookies before navigating — need to visit domain first
        if cookies:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Navigate to domain root to set cookies
            driver.get(f"{parsed.scheme}://{domain}")
            time.sleep(1)
            for c in cookies:
                if "=" in c:
                    name, _, value = c.partition("=")
                    driver.add_cookie({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": domain,
                    })

        driver.get(url)
        time.sleep(wait_seconds)

        html = driver.page_source
        title = driver.title

    except Exception as e:
        return tool_result(error=f"Browser fetch failed: {e}")

    return tool_result(data={"url": url, "html": html, "title": title})


WEB_TOOLS = [web_search, fetch_url, webscrape, find_all, find_download_link, find_allowed_routes, browser_fetch]
