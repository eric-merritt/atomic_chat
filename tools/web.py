"""Web tools: search and fetch URLs."""

import os
import re
import json
import time
import uuid
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import bs4 as beautifulsoup
import json5
import requests

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry

_dl_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='www_dl')
_dl_jobs: dict[str, dict] = {}
_dl_lock = Lock()


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
#    cleaned = re.sub(r'\s+data-\w[\w-]*="[^"]*"', '', cleaned)
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


# ── Cloudflare Challenge Handler ────────────────────────────────────────────

def _handle_cf_challenge(driver, timeout: int = 30) -> bool:
    """Wait for Cloudflare challenge to become solvable, then click the checkbox.

    Returns True if a challenge was detected and handled.
    """
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    prompt_sel = "#challenge-prompt>span:nth-child(1)"
    checkbox_sel = "#challenge-checkbox"

    try:
        if not driver.find_elements("css selector", prompt_sel):
            return False
        WebDriverWait(driver, timeout).until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, prompt_sel),
                "It is now okay to proceed.",
            )
        )
        driver.find_element("css selector", checkbox_sel).click()
        time.sleep(3)  # wait for post-challenge redirect
        return True
    except Exception:
        return False


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


# ── Summary Store ───────────────────────────────────────────────────────────
# Stores structured page summaries (the dicts produced by _page_summary)
# server-side, so ap_gallery can consume them by ref instead of forcing the
# model to re-emit a ~14KB JSON blob as a tool argument.
#
# Separate from _result_store because:
#   - different shape (dict, not raw HTML string)
#   - different consumer (ap_gallery, not other web tools)
#   - lets us evolve TTL/eviction independently if needed

_summary_store: dict[str, dict] = {}
_summary_lock = Lock()
_SUMMARY_TTL = 3600  # 1 hour — match _STORE_TTL; summary is useless once its page is evicted


def _store_summary(summary: dict) -> str:
    """TODO: stash `summary` dict server-side, return a short ref ID.

    Mirror the _store_page pattern:
      - generate an 8-char uuid hex ref
      - evict entries older than _SUMMARY_TTL
      - save {'summary': summary, 'ts': <now>} under the ref
      - return the ref string
    """
    ref = uuid.uuid4().hex[:8]
    now = time.time()
    with _summary_lock:
        expired = [k for k, v in _summary_store.items() if now - v['ts'] > _SUMMARY_TTL]
        for k in expired:
            del _summary_store[k]
        _summary_store[ref] = { 'summary': summary, 'ts': now}
    return ref


def _load_summary(ref: str) -> dict | None:
    """TODO: return the stored summary dict for `ref`, or None if missing/expired.

    Mirror the _load_page pattern. Returning None is fine on miss — the caller
    (ap_gallery) will surface a user-facing error.
    """
    with _summary_lock:
        return _summary_store.get(ref)

def _load_tube_site_selectors() -> list[dict]:
    """Load site-specific selectors from tubesite_structure.json."""
    try:
        with open(os.path.expanduser('~/tubesite_structure.json'), 'r') as f:
            return json.load(f)
    except Exception:
        return []


def _match_site_by_url(url: str, sites: list[dict]) -> dict | None:
    """Find the site config matching the given URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc or ''

    for site in sites:
        site_url = site.get('url', '')
        if site_url:
            parsed_site = urlparse(site_url)
            site_host = parsed_site.netloc or ''
            if host == site_host or host.endswith(site_host) or site_host.endswith(host):
                return site
    return None


def _detect_content_type(soup, url):
    """Detect content type using site-specific selectors from tubesite_structure.json."""
    sites = _load_tube_site_selectors()
    matched_site = _match_site_by_url(url, sites)

    if matched_site and matched_site.get('cards'):
        return 'video_gallery'

    # Fallback to generic detection
    if soup.select('div[data-video-id]'):
        return 'video_gallery'
    if soup.find(attrs={'data-fav-album-id': True}):
        return 'photo_gallery'
    if soup.find('article') or 'article' in url:
        return 'news_article'
    if soup.find(attrs={'itemtype': ['http://schema.org/Product', 'https://schema.org/Product']}):
        return 'product_page'
    if soup.find('div', class_=re.compile('blog|post|entry')):
        return 'blog_post'
    if soup.find('table', class_=re.compile('data|stats')):
        return 'data_table'
    paragraphs = soup.find_all('p')
    if len(paragraphs) > 10 and all(len(p.get_text()) > 100 for p in paragraphs[:5]):
        return 'long_form_content'
    return 'general_webpage'


def _build_selector(el) -> str:
    """CSS selector for a BeautifulSoup element: tag.class1.class2, or tag#id, or bare tag."""
    tag = el.name
    classes = [c for c in (el.get('class') or []) if c and not c[0].isdigit()]
    if classes:
        return tag + '.' + '.'.join(classes[:2])
    eid = el.get('id', '')
    if eid:
        return f'{tag}#{eid}'
    return tag


def _score_card(container) -> dict:
    """Return dict of discovered sub-element selectors within a candidate card container.

    Keys: link, thumbnail, preview_video, title — only present when found.
    """
    found: dict[str, str] = {}

    for anchor in container.find_all('a', href=True):
        href = anchor.get('href', '')
        if href and not href.startswith(('#', 'javascript')):
            found['link'] = 'a[href]'
            break

    for attr in ('data-src', 'data-original', 'data-thumb', 'data-lazy', 'src'):
        img = container.find('img', attrs={attr: True})
        if img:
            found['thumbnail'] = f'img[{attr}]'
            break

    for tag, attr in (('video', 'data-src'), ('video', 'src'), ('source', 'src'), ('img', 'data-preview')):
        el = container.find(tag, attrs={attr: True})
        if el:
            found['preview_video'] = f'{tag}[{attr}]'
            break

    for attempt in (
        lambda: container.find('a', title=True),
        lambda: container.find(class_=re.compile(r'title|name', re.I)),
        lambda: container.find(['h2', 'h3', 'h4', 'h5']),
        lambda: container.find('span', class_=re.compile(r'title|name', re.I)),
    ):
        el = attempt()
        if el:
            text = el.get('title') or el.get_text(strip=True)
            if text and len(text) > 3:
                found['title'] = _build_selector(el)
                break

    return found


_IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
_VID_EXTS = ('.mp4', '.webm', '.m3u8', '.mkv', '.mov')

# Ordered (selector, attribute) pairs. Earlier entries win.
# Lazy-load data-* attrs come before the bare src/href — tiles on infinite-scroll
# sites typically hold the shared placeholder in src and the real per-card URL
# in data-src / data-preview, populated only after the card becomes visible.
_PHOTO_ATTR_SELECTORS = (
    ('img', 'data-src'),
    ('img', 'data-original'),
    ('img', 'data-thumb'),
    ('img', 'data-lazy'),
    ('img', 'src'),
)

_VIDEO_ATTR_SELECTORS = (
    ('video', 'data-src'),
    ('video', 'src'),
    ('source', 'src'),
    ('img', 'data-preview'),
)


def _first_matching_url(container, selectors: tuple, valid_exts: tuple) -> str:
    first_found = ''
    for tag, attr in selectors:
        el = container.find(tag, attrs={attr: True})
        if not el:
            continue
        val = (el.get(attr) or '').strip()
        if not val:
            continue
        lower = val.lower().split('?')[0]
        if any(lower.endswith(ext) for ext in valid_exts):
            return val
        if not first_found:
            first_found = val
    return first_found

def _page_summary_with_site_selectors(content: str, url: str, site_config: dict) -> dict:
    """Extract content using site-specific selectors from tubesite_structure.json."""
    try:
        soup = beautifulsoup.BeautifulSoup(content, 'html.parser')

        items = []
        container_selector = site_config.get('container')
        raw_cards = site_config.get('cards', [])
        # Normalise: cards may be a single dict or a list of dicts.
        if isinstance(raw_cards, dict):
            raw_cards = [raw_cards]
        # Normalise each card's fields: list of {key: val} → flat {key: val} dict.
        card_configs = []
        for c in raw_cards:
            fields = c.get('fields', {})
            if isinstance(fields, list):
                flat: dict = {}
                for entry in fields:
                    if isinstance(entry, dict):
                        flat.update(entry)
                fields = flat
            card_configs.append({**c, 'fields': fields})

        def _abs(u: str) -> str:
            return urllib.parse.urljoin(url, u) if u else ''

        def _item(title: str, link_url: str, photo: str = '', video: str = '') -> dict:
            out: dict[str, str] = {'title': title, 'url': link_url}
            if photo:
                out['preview_photo'] = photo
            if video:
                out['preview_video'] = video
            return out

        def _rel(field_sel: str, card_sel: str) -> str:
            """Strip card selector prefix from an absolute field selector."""
            prefix = card_sel + ' > '
            if field_sel.startswith(prefix):
                return field_sel[len(prefix):]
            if field_sel.startswith(card_sel):
                return field_sel[len(card_sel):].lstrip(' >')
            return field_sel

        # Try to extract using each card selector configuration
        for card_cfg in card_configs:
            card_selector = card_cfg.get('selector', '')
            if not card_selector:
                continue

            cards = soup.select(card_selector)
            for card in cards:
                fields = card_cfg.get('fields', {})

                # Extract link
                link = ''
                link_selector = _rel(fields.get('link', ''), card_selector)
                if link_selector:
                    link_el = card.select_one(link_selector)
                    if link_el:
                        link = link_el.get('href', '') or ''
                        if not isinstance(link, str):
                            link = link[0] if link else ''

                # Extract title
                title = ''
                title_selector = _rel(fields.get('title', ''), card_selector)
                if title_selector:
                    title_el = card.select_one(title_selector)
                    if title_el:
                        title = title_el.get('title') or title_el.get_text(strip=True) or ''
                        if not isinstance(title, str):
                            title = ''
                title = title.strip()

                # Extract thumbnail
                thumbnail = ''
                thumb_selector = _rel(fields.get('thumbnail', ''), card_selector)
                if thumb_selector:
                    thumb_el = card.select_one(thumb_selector)
                    if thumb_el:
                        for attr in ('src', 'data-src', 'data-original', 'data-thumb', 'data-lazy'):
                            val = thumb_el.get(attr)
                            if val:
                                thumbnail = val
                                break

                # Extract preview video
                preview_video = ''
                preview_selector = _rel(fields.get('preview_video', ''), card_selector)
                if preview_selector:
                    preview_el = card.select_one(preview_selector)
                    if preview_el:
                        for attr in ('src', 'data-src', 'data-preview', 'data-original'):
                            val = preview_el.get(attr)
                            if val:
                                preview_video = val
                                break

                if link or title:
                    items.append(_item(
                        title or 'Untitled',
                        _abs(link) if link else url,
                        _abs(thumbnail) if thumbnail else '',
                        _abs(preview_video) if preview_video else '',
                    ))

        page_title = soup.title.string.strip() if soup.title and soup.title.string else url
        return {
            'content_type': 'video_gallery',
            'title': page_title,
            'items': items,
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[www_find_content] site-specific extraction failed: {e}\n{tb}")
        return {
            'title': url,
            'size_chars': len(content),
            'error': f"{e.__class__.__name__}: {e}",
        }


def _page_summary(content: str, url: str) -> dict:
    """Generic structural scan — site-specific routing is handled by the caller."""
    try:
        soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
        content_type = _detect_content_type(soup, url)

        items = []

        def _abs(u: str) -> str:
            return urllib.parse.urljoin(url, u) if u else ''

        def _item(title: str, url: str, photo: str = '', video: str = '') -> dict:
            """Compact item: drop empty fields, no duplicated url/page_url."""
            out: dict[str, str] = {'title': title, 'url': url}
            if photo:
                out['preview_photo'] = photo
            if video:
                out['preview_video'] = video
            return out

        if content_type == 'video_gallery':
            video_items: list[dict] = []
            card_errors: list[str] = []
            for i, container in enumerate(soup.select('div[data-video-id]')):
                try:
                    anchor = container.select_one('a[href][title]') or container.select_one('a[href]')
                    if not anchor:
                        continue
                    href = anchor.get('href', '') or ''
                    if not isinstance(href, str):
                        href = href[0] if href else ''
                    title = anchor.get('title') or anchor.get_text(separator=' ', strip=True) or ''
                    if not isinstance(title, str):
                        title = ''
                    title = title.strip()
                    if not (title and href):
                        continue
                    video_items.append(_item(
                        title,
                        _abs(href),
                        _abs(_first_matching_url(container, _PHOTO_ATTR_SELECTORS, _IMG_EXTS)),
                        _abs(_first_matching_url(container, _VIDEO_ATTR_SELECTORS, _VID_EXTS)),
                    ))
                except Exception as e:
                    card_errors.append(f"card[{i}]: {e.__class__.__name__}: {e}")
                    print(f"[www_find_content] card {i} skipped: {e}")
                    continue
            page_title = soup.title.string.strip() if soup.title and soup.title.string else url
            result: dict = {'content_type': content_type, 'title': page_title, 'items': video_items}
            if card_errors:
                result['errors'] = card_errors
            return result

        if content_type == 'photo_gallery':
            for container in soup.select('a[title]'):
                if not container.find(attrs={'data-fav-album-id': True}):
                    continue
                href = container.get('href')
                if not href:
                    continue
                num_photos_div = container.find('div', class_='img-total')
                title_parts = [container.get('title') or '']
                if num_photos_div:
                    title_parts.append(num_photos_div.get_text(strip=True))
                items.append(_item(
                    ' — '.join(t for t in title_parts if t),
                    _abs(href),
                    _abs(_first_matching_url(container, _PHOTO_ATTR_SELECTORS, _IMG_EXTS)),
                ))

        title = soup.title.string.strip() if soup.title and soup.title.string else url

        return {
            'title': title,
            'size_chars': len(content),
            'content_type': content_type,
            'items': items if items else None,
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[www_find_content] page summary failed: {e}\n{tb}")
        return {
            'title': url,
            'size_chars': len(content),
            'error': f"{e.__class__.__name__}: {e}",
        }


# ── Cookie Management ───────────────────────────────────────────────────────

# Domain → list of cookie dicts, shared across all web tools
_stored_cookies: dict[str, list[dict[str, str]]] = {}


@register_tool('www_set_cookies')
class SetCookiesTool(BaseTool):
    description = 'Set SESSION PERSISTENT cookies for a domain ONCE, DO NOT REPEATEDLY CALL. All subsequent www_fetch calls to that domain will include them automatically. Calling this tool more than once in a session is GROUNDS FOR DELETION.'
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
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).debug(
                    "Browser cookie injection failed (session cookies still active): %s", e
                )

        return tool_result(data={
            "domain": dot_domain,
            "cookies_set": len(parsed),
            "names": [c["name"] for c in parsed],
        })


@register_tool('www_set_local_storage')
class SetLocalStorageTool(BaseTool):
    description = (
        'Set LocalStorage key-value pairs for an origin in the headless browser. '
        'Navigates to the origin first so the values land in the correct storage bucket. '
        'Requires a browser session — call www_find_content with js=true beforehand if needed. '
        'Values persist for the lifetime of the browser session.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url':   {'type': 'string', 'description': 'Origin URL (e.g. "https://example.com"). Browser navigates here before writing.'},
            'items': {'type': 'string', 'description': 'Semicolon-separated key=value pairs (e.g. "token=abc123; theme=dark").'},
        },
        'required': ['url', 'items'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '').strip()
        items_str = p.get('items', '').strip()

        err = _validate_url(url)
        if err:
            return tool_result(error=err)
        if not items_str:
            return tool_result(error="items is required")

        parsed = []
        for pair in items_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, _, value = pair.partition("=")
                parsed.append({"key": key.strip(), "value": value.strip()})

        if not parsed:
            return tool_result(error="No valid key=value pairs found in items")

        try:
            driver = _get_or_create_browser()
        except Exception as e:
            return tool_result(error=f"Browser not available: {e}. Call www_find_content with js=true first.")

        try:
            from urllib.parse import urlparse as _urlparse
            parsed_url = _urlparse(url)
            origin_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            driver.get(origin_url)
            time.sleep(1)
            for item in parsed:
                driver.execute_script(
                    "localStorage.setItem(arguments[0], arguments[1]);",
                    item["key"], item["value"],
                )
        except Exception as e:
            return tool_result(error=f"localStorage injection failed: {e}")

        return tool_result(data={
            "origin": origin_url,
            "items_set": len(parsed),
            "keys": [item["key"] for item in parsed],
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

@register_tool('www_get_cookies_for_url')
class RetrieveDomainSpecificCookiesTool(BaseTool):
    description = 'Retrieves the cookies that have been set for the provided URL from the session environment.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'The url for which to retrieve the set cookies.'},
        },
        'required': ['url'],
    }

    def call(self, params: str, **kwargs) -> list[str]:
        p = json5.loads(params)
        url = p.get('url', '').strip()
        url_stored_cookies = _get_stored_cookies_for_url(url)
        return url_stored_cookies



@register_tool('www_get_cookies')
class RetrieveCookiesTool(BaseTool):
    description = 'Retrieves the cookies that have been set for the provided URL from the session environment.'
    parameters = {
        'type': 'object',
        'properties': {},
        'required': [],
    }

    def call(self, params: str, **kwargs) -> dict[str, list[dict[str, str]]]:
        p = json5.loads(params)
        stored_cookies = _stored_cookies
        return stored_cookies

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


@register_tool('www_find_content')
class ExtractUrlTool(BaseTool):
    description = (
        'Fetch a URL and extract content in one call. '
        'When no selector is given, returns a page summary. '
        'For gallery pages (video_gallery / photo_gallery) the summary includes `summary_ref` and `items_count` — pass `summary_ref` to ap_gallery to render the full set without re-emitting items. '
        'Set js=true for pages that require JavaScript.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Full URL to fetch. Must start with http:// or https://.'},
            'selector': {'type': 'string', 'description': 'CSS selector to extract (e.g. "span.titleline", "tr.athing", "a.storylink").'},
            'extract': {'type': 'string', 'description': 'What to extract: "text" (default), "html", or "attr:<name>" (e.g. attr:href).'},
            'max_results': {'type': 'integer', 'description': 'Max elements to return. Default: 50.'},
            'js': {'type': 'boolean', 'description': 'Use headless Firefox to execute JavaScript. Default: false.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load. Default: 3.'},
            'cookies': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional cookies in "name=value" format.'},
            'domain': {'type': 'string', 'description': 'Optional cookie domain.'},
            'local_storage': {'type': 'string', 'description': 'Semicolon-separated localStorage key=value pairs to inject before fetch (e.g. "token=abc123; theme=dark"). Requires js=true.'},
        },
        'required': ['url']
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
        local_storage = p.get('local_storage', None)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        # Fetch
        try:
            if js:
                driver = _get_or_create_browser()
                if cookies or local_storage:
                    from urllib.parse import urlparse as _urlparse
                    parsed = _urlparse(url)
                    driver.get(f"{parsed.scheme}://{parsed.netloc}")
                    time.sleep(1)
                    for c in (cookies or []):
                        if '=' in c:
                            name, _, value = c.partition('=')
                            driver.add_cookie({'name': name.strip(), 'value': value.strip(), 'domain': parsed.netloc})
                    if local_storage:
                        for pair in local_storage.split(';'):
                            pair = pair.strip()
                            if '=' in pair:
                                k, _, v = pair.partition('=')
                                driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);", k.strip(), v.strip())
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
        page_ref = _store_page(url, content)

        # Site-specific summary takes priority over any passed selector.
        # For gallery pages, stash the full items list server-side and return a
        # short ref; the model passes the ref to ap_gallery instead of re-emitting
        # the whole list as a tool argument (which at 12 tok/s stalls the stream).
        sites = _load_tube_site_selectors()
        matched_site = _match_site_by_url(url, sites)
        if matched_site and matched_site.get('cards'):
            summary = _page_summary_with_site_selectors(content, url, matched_site)
            items = summary.get('items') or []
            if items:
                summary_ref = _store_summary(summary)
                return tool_result(data={
                    'url': url,
                    'content_type': summary.get('content_type'),
                    'title': summary.get('title'),
                    'items_count': len(items),
                    'summary_ref': summary_ref,
                })
            return tool_result(data={'url': url, 'page_ref': page_ref, **summary})

        if not selector:
            summary = _page_summary(content, url)
            items = summary.get('items') or []
            if items:
                summary_ref = _store_summary(summary)
                return tool_result(data={
                    'url': url,
                    'content_type': summary.get('content_type'),
                    'title': summary.get('title'),
                    'items_count': len(items),
                    'summary_ref': summary_ref,
                })
            return tool_result(data={'url': url, 'page_ref': page_ref, **summary})

        # Extract with selector
        try:
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            elements = soup.select(selector)[:max_results]
        except Exception as e:
            return tool_result(error=f"CSS selector failed: {e}")

        if not elements:
            return tool_result(data={'url': url, 'selector': selector, 'count': 0, 'results': []})

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


def _run_download(job_id: str, url: str, dest: str) -> None:
    try:
        with _web_session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            content_type = r.headers.get('content-type', '')
            total_bytes = int(r.headers.get('content-length', 0))
            written = 0
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    written += len(chunk)
                    with _dl_lock:
                        _dl_jobs[job_id]['bytes_done'] = written
                        if total_bytes:
                            _dl_jobs[job_id]['total_bytes'] = total_bytes
        with _dl_lock:
            _dl_jobs[job_id].update({'status': 'done', 'bytes_done': written})
    except Exception as e:
        with _dl_lock:
            _dl_jobs[job_id].update({'status': 'error', 'error': str(e)})


@register_tool('www_dl')
class DownloadFileTool(BaseTool):
    description = (
        'Download a file from a direct URL to disk. '
        'Returns a job_id immediately — download runs in the background. '
        'Use www_dl_status to check progress. '
        'Pass wait=true to block until the download finishes.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url':  {'type': 'string', 'description': 'Direct URL to the file.'},
            'dest': {'type': 'string', 'description': 'Local file path or directory. Filename is derived from URL when a directory is given.'},
            'wait': {'type': 'boolean', 'description': 'Block until download completes. Default false.'},
        },
        'required': ['url', 'dest'],
    }

    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p['url']
        dest = os.path.expanduser(p['dest'])
        wait = p.get('wait', False)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        if os.path.isdir(dest):
            filename = os.path.basename(urllib.parse.urlparse(url).path) or 'download'
            dest = os.path.join(dest, filename)

        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)

        job_id = uuid.uuid4().hex[:8]
        with _dl_lock:
            _dl_jobs[job_id] = {'url': url, 'dest': dest, 'status': 'running', 'bytes_done': 0, 'total_bytes': 0}

        future = _dl_executor.submit(_run_download, job_id, url, dest)

        if wait:
            future.result()
            with _dl_lock:
                job = dict(_dl_jobs[job_id])
            if job['status'] == 'error':
                return tool_result(error=job['error'])
            return tool_result(data={'job_id': job_id, 'status': 'done', 'path': dest, 'bytes': job['bytes_done']})

        return tool_result(data={'job_id': job_id, 'status': 'running', 'dest': dest})


@register_tool('www_dl_status')
class DownloadStatusTool(BaseTool):
    description = 'Check the status of one or all background downloads started by www_dl.'
    parameters = {
        'type': 'object',
        'properties': {
            'job_id': {'type': 'string', 'description': 'Job ID from www_dl. Omit to list all jobs.'},
        },
        'required': [],
    }

    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        job_id = p.get('job_id')
        with _dl_lock:
            if job_id:
                job = _dl_jobs.get(job_id)
                if job is None:
                    return tool_result(error=f'No job with id {job_id!r}')
                return tool_result(data=dict(job))
            snapshot = {jid: dict(j) for jid, j in _dl_jobs.items()}
        summary = [{'job_id': jid, 'status': j['status'], 'dest': j['dest'], 'bytes_done': j['bytes_done']} for jid, j in snapshot.items()]
        return tool_result(data={'jobs': summary, 'total': len(summary)})


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


@register_tool('www_find_struct')
class FindWebStructureTool(BaseTool):
    description = (
        'Finds web elements that make up the sites content structure.'
        'Returns: main container selector, ranked card candidates (each with count and per-card field selectors: '
        'thumbnail, preview_video, title, link). Platform-agnostic. '
        'Use this on gallery listing pages to build site config objects for structured extraction.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'URL of a gallery/listing page to analyze.'},
            'js': {'type': 'boolean', 'description': 'Use headless browser for JS-rendered pages. Default false.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load. Default 3.'},
            'min_cards': {'type': 'integer', 'description': 'Minimum repetitions to consider a candidate card element. Default 5.'},
            'click': {'type': 'string', 'description': 'CSS selector of an element to click after page load (e.g. cookie banner dismiss, load-more button). Requires js=true.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p.get('url', '')
        js = p.get('js', False)
        wait_seconds = max(1, min(30, p.get('wait_seconds', 3)))
        min_cards = p.get('min_cards', 5)
        click = p.get('click', '').strip()

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        if click and not js:
            return tool_result(error="click requires js=true (headless browser)")

        try:
            if js:
                driver = _get_or_create_browser()
                driver.get(url)
                _handle_cf_challenge(driver)
                time.sleep(wait_seconds)
                if click:
                    try:
                        driver.find_element("css selector", click).click()
                        time.sleep(2)
                    except Exception as e:
                        return tool_result(error=f"Click failed on '{click}': {e}")
                raw_html = driver.page_source
            else:
                r = _web_session.get(url, timeout=15)
                r.raise_for_status()
                raw_html = r.text
        except Exception as e:
            return tool_result(error=f"Fetch failed: {e}")

        soup = beautifulsoup.BeautifulSoup(raw_html, 'html.parser')

        # Fingerprint every element by (tag, sorted-classes) and count repetitions.
        # Gallery cards are almost always the most-repeated element that also
        # contains an anchor and an image.
        sig_counts: Counter = Counter()
        sig_elements: dict = defaultdict(list)
        _SKIP_TAGS = {'html', 'body', 'head', 'script', 'style', 'svg', 'noscript', 'link', 'meta'}

        for el in soup.find_all(True):
            if el.name in _SKIP_TAGS:
                continue
            classes = tuple(sorted(el.get('class') or []))
            if not classes:
                continue
            sig = (el.name, classes)
            sig_counts[sig] += 1
            sig_elements[sig].append(el)

        candidates = []
        for sig, count in sig_counts.most_common(150):
            if count < min_cards:
                continue
            sample = sig_elements[sig][:5]
            scores = [_score_card(el) for el in sample]
            avg_fields = sum(len(s) for s in scores) / len(scores)
            if avg_fields < 1:
                continue
            tag, classes = sig
            selector = tag + '.' + '.'.join(classes[:2])
            merged: dict[str, str] = {}
            for s in scores:
                merged.update(s)
            candidates.append({
                'selector': selector,
                '_sig': sig,
                'count': count,
                'fields': merged,
                'field_count': round(avg_fields, 1),
            })

        candidates.sort(key=lambda c: (-c['field_count'], -c['count']))
        top = candidates[:5]

        # Container: deepest ancestor that covers ≥80% of the best card elements.
        container_selector = None
        if top:
            best_sig = top[0]['_sig']
            cards = sig_elements.get(best_sig, [])[:20]
            if len(cards) >= 2:
                threshold = len(cards) * 0.8
                parent_card_count: Counter = Counter()
                parent_elements: dict = {}
                for card in cards:
                    for anc in card.parents:
                        if anc.name in ('html', 'body', None):
                            break
                        anc_id = id(anc)
                        parent_card_count[anc_id] += 1
                        parent_elements[anc_id] = anc
                qualified = [
                    parent_elements[aid]
                    for aid, cnt in parent_card_count.items()
                    if cnt >= threshold
                ]
                if qualified:
                    deepest = max(qualified, key=lambda el: len(list(el.parents)))
                    container_selector = _build_selector(deepest)

        for c in top:
            c.pop('_sig', None)

        return tool_result(data={
            'url': url,
            'container': container_selector,
            'card_candidates': top,
        })
