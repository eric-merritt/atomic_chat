"""Web tools: search and fetch URLs."""

import os
import re
import json
import time
import urllib.request
import urllib.parse

import bs4 as beautifulsoup
import json5
import requests

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry


# ── Shared session for cookie persistence across tool calls ──────────────────
_web_session = requests.Session()
_web_session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"})


def _apply_cookies(url: str, cookies: list[str] | None, domain: str | None = None):
    """Set cookies on the shared session with proper domain scoping.

    If domain is not provided, it is derived from the URL (e.g.
    "https://www.example.com/page" → ".example.com").  The leading dot
    is added automatically so cookies match the root domain and all
    subdomains, which is how browsers handle domain cookies.
    """
    if not cookies:
        return
    if not domain:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        parts = host.split(".")
        # strip www / subdomain: keep last two segments (or all if already bare)
        domain = "." + ".".join(parts[-2:]) if len(parts) > 2 else "." + host
    elif not domain.startswith("."):
        domain = "." + domain
    for c in cookies:
        if "=" in c:
            name, _, value = c.partition("=")
            _web_session.cookies.set(name.strip(), value.strip(), domain=domain)


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


# ── Cookie Management ───────────────────────────────────────────────────────

# Domain → list of cookie dicts, shared across all web tools
_stored_cookies: dict[str, list[dict[str, str]]] = {}


@register_tool('www_cookies')
class SetCookiesTool(BaseTool):
    description = 'Set cookies for a domain. All subsequent www_fetch, www_scrape, and www_browse calls to that domain will include them automatically.'
    parameters = {
        'type': 'object',
        'properties': {
            'cookies': {'type': 'string', 'description': 'Semicolon-separated cookies in "name=value" format.'},
            'domain': {'type': 'string', 'description': 'Cookie domain (e.g. ".example.com").'},
        },
        'required': ['cookies', 'domain'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        cookies_str = p.get('cookies', '').strip()
        domain = p.get('domain', '').strip()

        if not cookies_str:
            return tool_result(error="cookies is required")
        if not domain:
            return tool_result(error="domain is required")

        dot_domain = domain if domain.startswith(".") else "." + domain

        parsed = []
        for pair in cookies_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, _, value = pair.partition("=")
                parsed.append({"name": name.strip(), "value": value.strip()})

        if not parsed:
            return tool_result(error="No valid name=value cookie pairs found")

        _apply_cookies("https://" + domain.lstrip("."), [f"{c['name']}={c['value']}" for c in parsed], dot_domain)

        if _browser_driver is not None:
            try:
                driver = _browser_driver
                driver.get(f"https://{domain.lstrip('.')}")
                import time as _t
                _t.sleep(1)
                for c in parsed:
                    driver.add_cookie({"name": c["name"], "value": c["value"], "domain": dot_domain})
            except Exception:
                pass

        return tool_result(data={
            "domain": dot_domain,
            "cookies_set": len(parsed),
            "names": [c["name"] for c in parsed],
        })


def _validate_url(url: str) -> str | None:
    """Return error string if URL is invalid, None if ok."""
    if not url or not url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"
    return None


def _get_stored_cookies_for_url(url: str) -> list[str]:
    """Return stored cookies matching a URL's domain as name=value strings."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    result = []
    for domain, cookies in _stored_cookies.items():
        # Match .example.com against www.example.com, foo.example.com, etc.
        if host == domain.lstrip(".") or host.endswith(domain):
            for c in cookies:
                result.append(f"{c['name']}={c['value']}")
    return result


# ── Web Operations ───────────────────────────────────────────────────────────

@register_tool('www_ddg')
class WebSearchTool(BaseTool):
    description = 'Search the web using DuckDuckGo and return results.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search query string. Must be non-empty.'},
            'num_results': {'type': 'integer', 'description': 'Maximum number of results to return. Range: 1-20. Default: 5.'},
        },
        'required': ['query'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        num_results = p.get('num_results', 5)

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


@register_tool('www_fetch')
class FetchUrlTool(BaseTool):
    description = 'Fetch a URL and return plain text with all HTML tags stripped.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Full URL to fetch. Must start with http:// or https://.'},
            'max_chars': {'type': 'integer', 'description': 'Maximum characters to return. Range: 100-50000. Default: 5000.'},
            'cookies': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional list of cookie strings in "name=value" format.'},
            'domain': {'type': 'string', 'description': 'Optional cookie domain (e.g. ".example.com"). Auto-derived from url if omitted.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')
        max_chars = p.get('max_chars', 5000)
        cookies = p.get('cookies', None)
        domain = p.get('domain', None)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        try:
            _apply_cookies(url, cookies, domain)
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


@register_tool('www_scrape')
class WebscrapeTool(BaseTool):
    description = 'Fetch a URL via HTTP and return raw HTML. Does NOT execute JavaScript.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Full URL to fetch. Must start with http:// or https://.'},
            'cookies': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional list of cookie strings in "name=value" format.'},
            'domain': {'type': 'string', 'description': 'Optional cookie domain (e.g. ".example.com"). Auto-derived from url if omitted.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')
        cookies = p.get('cookies', None)
        domain = p.get('domain', None)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        try:
            _apply_cookies(url, cookies, domain)
            r = _web_session.get(url, timeout=15)
            r.raise_for_status()
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

        return tool_result(data={"url": url, "html": r.text})


@register_tool('www_find_all')
class FindAllTool(BaseTool):
    description = 'Parse HTML and find all elements matching a CSS selector or tag name.'
    parameters = {
        'type': 'object',
        'properties': {
            'html': {'type': 'string', 'description': 'Raw HTML string to parse.'},
            'target': {'type': 'string', 'description': 'CSS selector or tag name (e.g. "a", "img.lazy-loaded", "div.card > a", "#main").'},
        },
        'required': ['html', 'target'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        html = p.get('html', '')
        target = p.get('target', '')

        if not html or not html.strip():
            return tool_result(error="html must be a non-empty string")
        if not target or not target.strip():
            return tool_result(error="target must be a non-empty CSS selector or tag name")

        try:
            soup = beautifulsoup.BeautifulSoup(html, "html.parser")
            # Use CSS select — works for both selectors ("img.foo") and plain tags ("img")
            elements = soup.select(target)
            element_strings = [str(el) for el in elements]
        except Exception as e:
            return tool_result(error=f"HTML parsing failed: {e}")

        return tool_result(data={
            "target": target,
            "count": len(element_strings),
            "elements": element_strings,
        })


@register_tool('www_find_dl')
class FindDownloadLinkTool(BaseTool):
    description = 'Parse HTML for media download links (video, image, audio sources).'
    parameters = {
        'type': 'object',
        'properties': {
            'html': {'type': 'string', 'description': 'Raw HTML string to parse. If empty, url must be provided.'},
            'url': {'type': 'string', 'description': 'URL to fetch HTML from. Only used if html is empty.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        html = p.get('html', '')
        url = p.get('url', '')

        if not html and not url:
            return tool_result(error="Provide either html or url. Both cannot be empty.")

        if not html and url:
            err = _validate_url(url)
            if err:
                return tool_result(error=err)
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


@register_tool('www_find_routes')
class FindAllowedRoutesTool(BaseTool):
    description = "Fetch a website's robots.txt and return the allowed crawl paths."
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Base URL of the website (e.g. "https://example.com") or direct robots.txt URL.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

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


@register_tool('www_browse')
class BrowserFetchTool(BaseTool):
    description = 'Fetch a URL using a headless Firefox browser that executes JavaScript and returns the fully rendered HTML.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Full URL to fetch. Must start with http:// or https://.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after page load for JS to execute. Range: 1-30. Default: 3.'},
            'cookies': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional list of cookie strings in "name=value" format.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')
        wait_seconds = p.get('wait_seconds', 3)
        cookies = p.get('cookies', None)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

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


@register_tool('www_query')
class BrowserQueryTool(BaseTool):
    description = 'Run querySelectorAll on the current browser page and return matching elements.'
    parameters = {
        'type': 'object',
        'properties': {
            'selector': {'type': 'string', 'description': 'CSS selector (e.g. "img.lazy-loaded", "a.video-link", "div.card > h2").'},
            'attribute': {'type': 'string', 'description': 'Optional attribute to extract from each element (e.g. "href", "src", "textContent"). If empty, returns outerHTML.'},
        },
        'required': ['selector'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        selector = p.get('selector', '')
        attribute = p.get('attribute', '')

        if not selector or not selector.strip():
            return tool_result(error="selector must be a non-empty CSS selector")

        try:
            driver = _get_or_create_browser()
        except Exception as e:
            return tool_result(error=f"No browser session: {e}. Call browser_fetch first.")

        attr_js = f".getAttribute('{attribute}')" if attribute and attribute != "textContent" else ""
        if attribute == "textContent":
            attr_js = ".textContent"

        if attribute:
            js = f"""
            return Array.from(document.querySelectorAll({json.dumps(selector)}))
                .map(el => el{attr_js})
                .filter(v => v != null);
            """
        else:
            js = f"""
            return Array.from(document.querySelectorAll({json.dumps(selector)}))
                .map(el => el.outerHTML);
            """

        try:
            elements = driver.execute_script(js)
        except Exception as e:
            return tool_result(error=f"querySelectorAll failed: {e}")

        return tool_result(data={
            "selector": selector,
            "count": len(elements),
            "elements": elements,
        })


@register_tool('www_click')
class BrowserClickTool(BaseTool):
    description = 'Click an element on the current browser page.'
    parameters = {
        'type': 'object',
        'properties': {
            'selector': {'type': 'string', 'description': 'CSS selector for the element to click (e.g. "a.next-page", "button.download").'},
        },
        'required': ['selector'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        selector = p.get('selector', '')

        if not selector or not selector.strip():
            return tool_result(error="selector must be a non-empty CSS selector")

        try:
            driver = _get_or_create_browser()
        except Exception as e:
            return tool_result(error=f"No browser session: {e}. Call browser_fetch first.")

        try:
            element = driver.find_element("css selector", selector)
            element.click()
            time.sleep(2)
        except Exception as e:
            return tool_result(error=f"Click failed: {e}")

        return tool_result(data={
            "selector": selector,
            "url": driver.current_url,
            "title": driver.title,
        })
