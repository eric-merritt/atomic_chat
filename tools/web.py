"""Web tools: search and fetch URLs."""

import os
import re
import json
import time
import uuid
import urllib.parse
from threading import Lock

import bs4 as beautifulsoup
import json5
import requests

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry


def _strip_html_noise(html: str) -> str:
    """Strip non-structural noise from HTML for LLM consumption.

    Removes: <head>, <script>, <style>, <svg>, <noscript>, comments,
    inline style/onclick attrs, data- attrs. Keeps structural <body> content.
    """
    cleaned = re.sub(r'<head\b[^>]*>[\s\S]*?</head>', '', html, flags=re.IGNORECASE)
    cleaned = re.sub(r'<(script|style|svg|noscript)\b[^>]*>[\s\S]*?</\1>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<!--[\s\S]*?-->', '', cleaned)
    cleaned = re.sub(r'\s+style="[^"]*"', '', cleaned)
    cleaned = re.sub(r"\s+style='[^']*'", '', cleaned)
    cleaned = re.sub(r'\s+on\w+="[^"]*"', '', cleaned)
    cleaned = re.sub(r'\s+data-\w[\w-]*="[^"]*"', '', cleaned)
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    return cleaned.strip()



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


# ── Result Store ────────────────────────────────────────────────────────────
# Stores fetched page content server-side. Agent receives a ref handle and
# queries into it; the raw content never enters the LLM context directly.

_result_store: dict[str, dict] = {}
_store_lock = Lock()
_STORE_TTL = 3600  # 1 hour


def _store_page(url: str, content: str) -> str:
    """Store stripped page content and return a short ref ID."""
    ref = uuid.uuid4().hex[:8]
    now = time.time()
    with _store_lock:
        expired = [k for k, v in _result_store.items() if now - v['ts'] > _STORE_TTL]
        for k in expired:
            del _result_store[k]
        _result_store[ref] = {'url': url, 'content': content, 'ts': now}
    return ref


def _load_page(ref: str) -> dict | None:
    with _store_lock:
        return _result_store.get(ref)


def _page_summary(content: str, url: str) -> dict:
    """Structural scan of the page to give the agent enough to pick selectors.

    Returns title, headings, a sample of link texts + their CSS paths,
    and notable class/id patterns seen on the page.
    """
    try:
        soup = beautifulsoup.BeautifulSoup(content, 'html.parser')

        # Title
        title = soup.title.string.strip() if soup.title and soup.title.string else ''

        # Top headings (h1–h3, first 5)
        headings = [
            h.get_text(strip=True)
            for h in soup.find_all(['h1', 'h2', 'h3'])[:5]
            if h.get_text(strip=True)
        ]

        # Sample links — skip short nav links, prioritize substantive content links
        link_samples = []
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            if not text or len(text) < 15:
                continue
            parts = []
            for el in [a.parent, a]:
                if el and el.name:
                    cls = ' '.join(el.get('class', []))[:40]
                    eid = el.get('id', '')
                    if eid:
                        parts.append(f'#{eid}')
                    elif cls:
                        parts.append(f'{el.name}.{cls.split()[0]}')
            selector_hint = ' > '.join(parts) if parts else a.name
            link_samples.append({'text': text[:80], 'selector_hint': selector_hint})
            if len(link_samples) >= 10:
                break

        # Notable class names on repeated elements (good selector candidates)
        from collections import Counter
        class_counts = Counter()
        for el in soup.find_all(True):
            for cls in el.get('class', []):
                class_counts[cls] += 1
        common_classes = [f'.{c}' for c, n in class_counts.most_common(12) if n > 2]

        return {
            'title': title or url,
            'size_chars': len(content),
            'headings': headings,
            'link_samples': link_samples,
            'common_classes': common_classes,
        }
    except Exception:
        return {'title': url, 'size_chars': len(content)}


# ── Cookie Management ───────────────────────────────────────────────────────

# Domain → list of cookie dicts, shared across all web tools
_stored_cookies: dict[str, list[dict[str, str]]] = {}


@register_tool('www_cookies')
class SetCookiesTool(BaseTool):
    description = 'Set cookies for a domain. All subsequent www_fetch calls to that domain will include them automatically.'
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

        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                hits = list(ddgs.text(query, max_results=num_results))
        except Exception as e:
            return tool_result(error=f"DuckDuckGo search failed: {e}")

        results = [{"text": h.get("body", ""), "url": h.get("href", ""), "title": h.get("title", "")} for h in hits]
        return tool_result(data={"query": query, "results": results})


@register_tool('www_extract')
class ExtractUrlTool(BaseTool):
    description = (
        'Fetch a URL and extract content in one call. '
        'Returns page structure (title, headings, link_samples, common_classes) when no selector is given — use that to choose a selector, then call again with selector to get content. '
        'Set js=true for pages that require JavaScript.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Full URL to fetch. Must start with http:// or https://.'},
            'selector': {'type': 'string', 'description': 'CSS selector to extract (e.g. "span.titleline", "tr.athing", "a.storylink"). Omit to get page structure summary first.'},
            'extract': {'type': 'string', 'description': 'What to extract: "text" (default), "html", or "attr:<name>" (e.g. attr:href).'},
            'max_results': {'type': 'integer', 'description': 'Max elements to return. Default: 50.'},
            'js': {'type': 'boolean', 'description': 'Use headless Firefox to execute JavaScript. Default: false.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load. Default: 3.'},
            'cookies': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional cookies in "name=value" format.'},
            'domain': {'type': 'string', 'description': 'Optional cookie domain.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')
        selector = p.get('selector', '')
        extract = p.get('extract', 'text')
        max_results = p.get('max_results', 50)
        js = p.get('js', False)
        wait_seconds = max(1, min(30, p.get('wait_seconds', 3)))
        cookies = p.get('cookies', None)
        domain = p.get('domain', None)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        # Fetch
        try:
            if js:
                driver = _get_or_create_browser()
                if cookies:
                    from urllib.parse import urlparse as _urlparse
                    parsed = _urlparse(url)
                    driver.get(f"{parsed.scheme}://{parsed.netloc}")
                    time.sleep(1)
                    for c in (cookies or []):
                        if '=' in c:
                            name, _, value = c.partition('=')
                            driver.add_cookie({'name': name.strip(), 'value': value.strip(), 'domain': parsed.netloc})
                driver.get(url)
                time.sleep(wait_seconds)
                raw_html = driver.page_source
            else:
                _apply_cookies(url, cookies, domain)
                r = _web_session.get(url, timeout=15)
                r.raise_for_status()
                raw_html = r.text
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

        content = _strip_html_noise(raw_html)
        _store_page(url, content)  # cache for potential www_find_dl use

        # No selector — return structure summary so agent can choose one
        if not selector:
            summary = _page_summary(content, url)
            return tool_result(data={'url': url, **summary,
                'note': 'No selector provided. Use link_samples selector_hints or common_classes to pick one, then call www_extract again with selector.'})

        # Extract with selector
        try:
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            elements = soup.select(selector)[:max_results]
        except Exception as e:
            return tool_result(error=f"CSS selector failed: {e}")

        if not elements:
            summary = _page_summary(content, url)
            return tool_result(data={'url': url, 'selector': selector, 'count': 0, 'results': [],
                'hint': 'No elements matched. Try one of these: ' + ', '.join(summary.get('common_classes', [])[:6])})

        if extract == 'text':
            results = [el.get_text(separator=' ', strip=True) for el in elements]
        elif extract == 'html':
            results = [str(el) for el in elements]
        elif extract.startswith('attr:'):
            attr = extract[5:]
            results = [el.get(attr, '') for el in elements]
        else:
            return tool_result(error=f"Unknown extract mode '{extract}'. Use text, html, or attr:<name>.")

        return tool_result(data={'url': url, 'selector': selector, 'count': len(results), 'results': results})


@register_tool('www_find_dl')
class FindDownloadLinkTool(BaseTool):
    description = 'Find media download links (video, image, audio sources) in a page by URL.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'URL of the page to search for media links.'},
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

        try:
            r = _web_session.get(url, timeout=15)
            r.raise_for_status()
            content = _strip_html_noise(r.text)
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

        try:
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
        except Exception as e:
            return tool_result(error=f"HTML parsing failed: {e}")

        links = []
        for tag_name in ('video', 'source', 'img', 'audio'):
            for el in soup.find_all(tag_name):
                src = el.get('src') or el.get('data-src') or ''
                if src:
                    links.append({'tag': tag_name, 'src': src})

        return tool_result(data={'url': url, 'links': links})


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
