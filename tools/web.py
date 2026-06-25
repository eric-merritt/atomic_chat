"""Web tools: search and fetch URLs."""

import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


import re
import json
import time
import uuid
import shutil
import subprocess
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
import bs4 as beautifulsoup
import json5
import requests

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry

_KNOWN_SITES_PATH = Path(__file__).parent.parent / "data" / "known_site_structures.json"
_USER_STRUCTURES_PATH = Path.home() / '.agent_known_structures.json'

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

_SUMMARY_TTL = 3600 * 24 * 7  # 7 days


def _get_user_id() -> str | None:
    try:
        from flask_login import current_user
        return current_user.id if current_user.is_authenticated else None
    except RuntimeError:
        return None


def _store_summary(summary: dict) -> str:
    from datetime import datetime, timezone
    from auth.db import SessionLocal
    import sqlalchemy as sa

    ref = uuid.uuid4().hex[:8]
    user_id = _get_user_id()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        db.execute(
            sa.text("DELETE FROM summary_refs WHERE created_at < NOW() - INTERVAL ':ttl seconds'"),
            {"ttl": _SUMMARY_TTL},
        )
        db.execute(
            sa.text("INSERT INTO summary_refs (ref, user_id, data, created_at) VALUES (:ref, :uid, :data, :ts)"),
            {"ref": ref, "uid": user_id, "data": json.dumps(summary), "ts": now},
        )
        db.commit()
    finally:
        db.close()
    return ref


def _load_summary(ref: str, user_id: str | None = None) -> dict | None:
    from auth.db import SessionLocal
    import sqlalchemy as sa

    uid = user_id or _get_user_id()
    db = SessionLocal()
    try:
        row = db.execute(
            sa.text("SELECT data FROM summary_refs WHERE ref = :ref AND user_id = :uid"),
            {"ref": ref, "uid": uid},
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        db.close()

_known_sites_cache: dict = {"mtime": -1.0, "data": []}
_known_sites_cache_lock = Lock()


def _load_tube_site_selectors() -> list[dict]:
    """Load site-specific selectors, merging shipped + user-local.

    User-local (~/.agent_known_structures.json) wins on URL collision.
    Shipped file (data/known_site_structures.json) is read-only.
    Cached by shipped-file mtime — re-reads when that file changes.
    """
    try:
        current_mtime = _KNOWN_SITES_PATH.stat().st_mtime
    except OSError:
        current_mtime = -1.0

    with _known_sites_cache_lock:
        if _known_sites_cache["mtime"] == current_mtime:
            return _known_sites_cache["data"]
        try:
            with open(_KNOWN_SITES_PATH, 'r') as fh:
                shipped = json.load(fh)
        except Exception:
            shipped = _known_sites_cache["data"] or []

        try:
            user_local = json.loads(_USER_STRUCTURES_PATH.read_text())
        except Exception:
            user_local = []

        merged: dict[str, dict] = {s['url']: s for s in shipped if s.get('url')}
        for entry in user_local:
            if entry.get('url'):
                merged[entry['url']] = entry

        result = list(merged.values())
        _known_sites_cache["mtime"] = current_mtime
        _known_sites_cache["data"] = result
        return result


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
    """Detect content type using site-specific selectors from known_site_structures.json."""
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


_IMG_EXTS = (
    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.svg',
    '.tiff', '.tif', '.ico', '.avif', '.heic', '.heif',
)
_VID_EXTS = (
    '.mp4', '.webm', '.m3u8', '.mkv', '.mov', '.avi', '.flv',
    '.wmv', '.ts', '.ogv',
)
_DOC_EXTS = (
    '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.rtf', '.csv', '.md', '.epub',
)
_BIN_EXTS = (
    '.exe', '.msi', '.msix', '.dmg', '.pkg', '.deb', '.rpm', '.AppImage',
    '.sh', '.bash', '.zsh', '.fish',
    '.py', '.rs', '.js', '.mjs', '.cjs', '.ts', '.jsx', '.tsx',
    '.go', '.rb', '.php', '.cs', '.cpp', '.c', '.h', '.java',
    '.kt', '.swift', '.lua', '.r', '.jl',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', '.zst',
)

_MEDIA_EXTS: dict[str, tuple] = {
    'video':    _VID_EXTS,
    'image':    _IMG_EXTS,
    'document': _DOC_EXTS,
    'binary':   _BIN_EXTS,
}

_MEDIA_TYPE_ALIASES: dict[str, str] = {
    'photo': 'image', 'photograph': 'image', 'picture': 'image', 'img': 'image',
    'movie': 'video', 'film': 'video', 'clip': 'video',
    'doc': 'document', 'text': 'document',
    'executable': 'binary', 'exe': 'binary', 'code': 'binary', 'script': 'binary',
}

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
    """Extract content using site-specific selectors from known_site_structures.json."""
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


# ── Credential-based login fallback ─────────────────────────────────────────

# Selector pairs for detecting and filling login forms
_LOGIN_SELECTORS = [
    # Common username/password fields
    ("input[type='email']", "input[type='password']"),
    ("input[name='email']", "input[name='password']"),
    ("input[name='username']", "input[name='password']"),
    ("input[name='user']", "input[name='pass']"),
    ("input[name='login']", "input[name='password']"),
    ("input[id='email']", "input[id='password']"),
    ("input[id='username']", "input[id='password']"),
    ("input[id='user']", "input[id='pass']"),
    ("input[id='login']", "input[id='password']"),
    ("input[autocomplete='username']", "input[autocomplete='current-password']"),
]

_LOGIN_BTN_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button.login-button",
    "button#login-submit",
    "input#login-submit",
    "form button",
]


def _try_credential_auth(url: str, driver, user_id: int = None) -> bool:
    """Try to log in using stored credentials when no cookies exist.

    Returns True if login succeeded, False otherwise.
    """
    from urllib.parse import urlparse, urljoin

    try:
        from auth.credentials import load_credentials
    except ImportError:
        return False

    # Find credential matching the URL's domain
    host = urlparse(url).hostname or ""
    domain = host.lstrip("www.")
    cred = None
    for alias, entry in load_credentials().items():
        cred_url = entry.get("url", "")
        cred_host = urlparse(cred_url).hostname or ""
        if cred_host == host or cred_host.endswith(domain) or domain.endswith(cred_host.lstrip("www.")):
            if entry.get("username") and entry.get("password"):
                cred = entry
                break

    if not cred:
        return False

    username = cred.get("username", "")
    password = cred.get("password", "")
    if not username or not password:
        return False

    # Try the URL itself first, then common login paths
    try_urls = [url]
    if url.count("/") <= 3:  # Only root URL
        try_urls.extend([
            urljoin(url, "/login"),
            urljoin(url, "/signin"),
            urljoin(url, "/auth"),
        ])

    for try_url in try_urls:
        try:
            driver.get(try_url)
            time.sleep(1)

            # Find username/password field pair
            for user_sel, pass_sel in _LOGIN_SELECTORS:
                user_fields = driver.find_elements("css selector", user_sel)
                pass_fields = driver.find_elements("css selector", pass_sel)
                if user_fields and pass_fields:
                    # Fill credentials
                    user_fields[0].clear()
                    user_fields[0].send_keys(username)
                    pass_fields[0].clear()
                    pass_fields[0].send_keys(password)

                    # Submit
                    for btn_sel in _LOGIN_BTN_SELECTORS:
                        btns = driver.find_elements("css selector", btn_sel)
                        if btns:
                            btns[0].click()
                            break
                    else:
                        # Fallback: press Enter in password field
                        from selenium.webdriver.common.keys import Keys
                        pass_fields[0].send_keys(Keys.RETURN)

                    time.sleep(3)

                    # Check if we're still on a login page (failed)
                    current = driver.current_url
                    if "login" in current.lower() or "signin" in current.lower():
                        continue  # Try next URL

                    # Success — cookies should now be in the browser session
                    # Capture them into _stored_cookies
                    _capture_browser_cookies(driver, host)
                    return True

        except Exception:
            continue  # Try next URL

    return False


def _capture_browser_cookies(driver, target_host: str) -> None:
    """Extract cookies from the browser session and store in _stored_cookies."""
    user_id = _get_user_id()
    if user_id is None:
        return

    try:
        all_cookies = driver.get_cookies()
        # Normalize to dot-domain
        domains_seen = set()
        for c in all_cookies:
            c_domain = c.get("domain", "")
            if not c_domain:
                c_domain = "." + target_host
            elif not c_domain.startswith("."):
                c_domain = "." + c_domain
            domains_seen.add(c_domain)

        from urllib.parse import urlparse
        host = target_host.lstrip("www.")
        parts = host.split(".")
        root_domain = "." + ".".join(parts[-2:]) if len(parts) > 2 else "." + host

        user_cookies = _stored_cookies.setdefault(user_id, {})
        for c in all_cookies:
            c_name = c.get("name", "")
            c_value = c.get("value", "")
            if not c_name:
                continue

            # Store under root domain
            if root_domain not in user_cookies:
                user_cookies[root_domain] = []

            # Upsert
            existing = user_cookies[root_domain]
            found = False
            for i, ec in enumerate(existing):
                if ec["name"] == c_name:
                    existing[i] = {"name": c_name, "value": c_value}
                    found = True
                    break
            if not found:
                existing.append({"name": c_name, "value": c_value})

    except Exception:
        pass


# ── Cookie Management ───────────────────────────────────────────────────────

# {user_id: {domain: [cookie dicts]}} — scoped to authenticated user
_stored_cookies: dict[int, dict[str, list[dict[str, str]]]] = {}


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


def _get_stored_cookies_for_url(url: str, user_id: int = None) -> list[str]:
    """Return stored cookies matching a URL's domain as name=value strings."""
    from urllib.parse import urlparse
    if user_id is None:
        user_id = _get_user_id()
    if user_id is None:
        return []
    user_cookies = _stored_cookies.get(user_id, {})
    host = urlparse(url).hostname or ""
    result = []
    for domain, cookies in user_cookies.items():
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
        user_id = _get_user_id()
        if user_id is None:
            return {}
        return _stored_cookies.get(user_id, {})


# ── Cookie sync from frontend (extension-collected) ─────────────────────────

def sync_cookies_from_frontend(domain: str, name: str, value: str, meta: dict | None = None, user_id: int = None):
    """Store a single cookie collected by the browser extension.

    Called by the /api/cookies/sync route. Populates _stored_cookies[user_id] so
    agent tools (www_fetch, www_find_content, etc.) can apply them.
    Also injects into the headless browser if one is active.
    """
    if user_id is None:
        user_id = _get_user_id()
    if user_id is None:
        return  # No authenticated user — skip
    dot_domain = domain if domain.startswith(".") else "." + domain

    # Store in per-user dict
    user_cookies = _stored_cookies.setdefault(user_id, {})
    if dot_domain not in user_cookies:
        user_cookies[dot_domain] = []
    # Upsert: replace if same name exists
    existing = user_cookies[dot_domain]
    for i, c in enumerate(existing):
        if c["name"] == name:
            existing[i] = {"name": name, "value": value}
            break
    else:
        existing.append({"name": name, "value": value})

    # Also apply to the shared requests session
    _apply_cookies(f"https://{dot_domain.lstrip('.')}", [f"{name}={value}"], dot_domain)

    # Inject into headless browser if active
    global _browser_driver
    if _browser_driver is not None:
        try:
            cookie_dict = {"name": name, "value": value, "domain": dot_domain}
            if meta:
                if meta.get("path"):
                    cookie_dict["path"] = meta["path"]
                if meta.get("secure") is not None:
                    cookie_dict["secure"] = meta["secure"]
                if meta.get("httpOnly") is not None:
                    cookie_dict["httpOnly"] = meta["httpOnly"]
                if meta.get("sameSite"):
                    cookie_dict["sameSite"] = meta["sameSite"]
                if meta.get("expirationDate"):
                    cookie_dict["expiry"] = int(meta["expirationDate"])
            _browser_driver.add_cookie(cookie_dict)
        except Exception:
            pass  # Best-effort for live browser


@register_tool('www_sync_cookies')
class SyncCookiesTool(BaseTool):
    description = (
        'Sync all cookies collected by the browser extension (from the frontend cookie store) '
        'into the headless browser session. Call this ONCE at the start of a browsing session '
        'to make all available cookies active. '
        'Returns the number of domains and cookies synced.'
    )
    parameters = {
        'type': 'object',
        'properties': {},
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        user_id = _get_user_id()
        user_cookies = _stored_cookies.get(user_id, {}) if user_id else {}
        if not user_cookies:
            return tool_result(data={"domains_synced": 0, "cookies_synced": 0, "note": "No cookies stored"})

        try:
            driver = _get_or_create_browser()
        except Exception as e:
            return tool_result(error=f"No browser session available: {e}")

        total_cookies = 0
        for domain, cookies in user_cookies.items():
            root = domain.lstrip(".")
            try:
                driver.get(f"https://{root}")
                time.sleep(0.5)
                for c in cookies:
                    driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": domain,
                    })
                    total_cookies += 1
            except Exception:
                pass  # Skip domains that fail to load

        return tool_result(data={
            "domains_synced": len(user_cookies),
            "cookies_synced": total_cookies,
        })

# ── Web Operations ───────────────────────────────────────────────────────────

@register_tool('www_search')
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
                # Check if we have cookies for this URL's domain
                user_id = _get_user_id()
                has_cookies = False
                if user_id:
                    from urllib.parse import urlparse as _urlparse
                    host = _urlparse(url).hostname or ""
                    user_cookies = _stored_cookies.get(user_id, {})
                    for d, ck in user_cookies.items():
                        if host == d.lstrip(".") or host.endswith(d):
                            has_cookies = True
                            break

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
                elif not has_cookies:
                    # No cookies — try credential-based login as fallback
                    _try_credential_auth(url, driver, user_id)

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
            soup_p = beautifulsoup.BeautifulSoup(content, 'html.parser')
            container = _find_page_nav(soup_p, _PAGINATION_CONTAINERS)
            pages = _extract_pages(container) if container else {}
            return tool_result(data={
                'url': url, 'page_ref': page_ref, **summary,
                **({"pagination": pages} if pages else {}),
            })

        # Extract with selector
        try:
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            elements = soup.select(selector)[:max_results]
        except Exception as e:
            return tool_result(error=f"CSS selector failed: {e}")

        if not elements:
            container = _find_page_nav(soup, _PAGINATION_CONTAINERS)
            pages = _extract_pages(container) if container else {}
            return tool_result(data={
                'url': url, 'selector': selector, 'count': 0, 'results': [],
                **({"pagination": pages} if pages else {}),
            })

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


_MAIN_CONTENT_SELECTORS = ['article', 'main', '[role="main"]', '#content', '#main', '.content', '.main']

def _find_page_nav(soup, class_fragments):
  """Return the first element whose class list contains any of the given
  fragments (case-insensitive substring match), or None. Used to locate a
  pagination container before extracting its page links."""
  for element in soup.find_all(class_=True):
    classes = ' '.join(element.get('class', [])).lower()
    if any(fragment.lower() in classes for fragment in class_fragments):
      return element
  return None


def _extract_pages(container):
  """Map page label → absolute href for every anchor in a pagination
  container. Skips anchors without an http(s) href so fragments and
  javascript: links are dropped. Returns {} when none qualify."""
  pages = {}
  for anchor in container.find_all('a', href=True):
    href = anchor['href']
    if not href.startswith('http'):
      continue
    label = anchor.get_text(strip=True)
    if label:
      pages[label] = href
  return pages


def _extract_main(soup):
  for sel in _MAIN_CONTENT_SELECTORS:
    node = soup.select_one(sel)
    if node:
      return node
  return soup.body or soup

def _extract_links(node, base_url):
  links = []
  for a in node.find_all('a', href=True):
    href = urllib.parse.urljoin(base_url, a['href'])
    text = a.get_text(separator=' ', strip=True)
    if href.startswith('http') and text:
      links.append({'text': text, 'href': href})
  return links


@register_tool('www_fetch')
class FetchPageTool(BaseTool):
  description = (
    'Fetch any URL and return structured page content without needing selectors. '
    'Returns title, description, headings, main text, links, and pagination if found. '
    'Use for unknown or new sites. Set js=true for JavaScript-rendered pages.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'url': {'type': 'string', 'description': 'Full URL to fetch.'},
      'js': {'type': 'boolean', 'description': 'Use headless Firefox for JS-rendered pages. Default: false.'},
      'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load. Default: 3.'},
      'max_text': {'type': 'integer', 'description': 'Max characters of main text to return. Default: 2000.'},
      'max_links': {'type': 'integer', 'description': 'Max links to return. Default: 30.'},
    },
    'required': ['url'],
  }

  @retry()
  def call(self, params: str, **kwargs) -> dict:
    p = json5.loads(params)
    url = p.get('url', '')
    js = p.get('js', False)
    wait_seconds = max(1, min(30, p.get('wait_seconds', 3)))
    max_text = p.get('max_text', 2000)
    max_links = p.get('max_links', 30)

    err = _validate_url(url)
    if err:
      return tool_result(error=err)

    try:
      if js:
        driver = _get_or_create_browser()
        driver.get(url)
        time.sleep(wait_seconds)
        raw_html = driver.page_source
      else:
        r = _web_session.get(url, timeout=15)
        r.raise_for_status()
        raw_html = r.text
    except Exception as e:
      return tool_result(error=f"Failed to fetch {url}: {e}")

    content = _strip_html_noise(raw_html)
    soup = beautifulsoup.BeautifulSoup(content, 'html.parser')

    title = soup.title.string.strip() if soup.title and soup.title.string else ''
    description = ''
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
      description = (meta_desc.get('content') or '').strip()

    headings = [
      h.get_text(separator=' ', strip=True)
      for h in soup.find_all(['h1', 'h2', 'h3'])
    ][:10]

    main = _extract_main(soup)
    text = main.get_text(separator=' ', strip=True)[:max_text]
    links = _extract_links(main, url)[:max_links]

    container = _find_page_nav(soup, _PAGINATION_CONTAINERS)
    pages = _extract_pages(container) if container else {}

    return tool_result(data={
      'url': url,
      'title': title,
      **({"description": description} if description else {}),
      **({"headings": headings} if headings else {}),
      'text': text,
      'links': links,
      **({"pagination": pages} if pages else {}),
    })


_MEDIA_URL_RE = re.compile(
    r'["\'\`]'
    r'(https?://[^"\'\`]+\.(?:m3u8|mp4|webm|mkv|mov|avi|flv|wmv|ts|ogv)(?:\?[^"\'\`]*)?)'
    r'["\'\`]',
    re.IGNORECASE,
)

_PLAY_SELECTORS = [
    '.jw-icon-display', '.jw-display-icon-container', '[aria-label="Play"]',
    '.play-button', 'button.play', '[data-role="play"]', '.vjs-big-play-button',
    '.video-js .vjs-play-control', 'video',
]

_INTERCEPT_JS = """
window.__captured_media = window.__captured_media || [];
(function() {
  var _fetch = window.fetch;
  window.fetch = function(u) {
    if (typeof u === 'string' && /\\.m3u8/i.test(u)) window.__captured_media.push(u);
    return _fetch.apply(this, arguments);
  };
  var _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u) {
    if (u && /\\.m3u8/i.test(u)) window.__captured_media.push(u);
    return _open.apply(this, arguments);
  };
})();
"""

_PLAYER_EXTRACT_JS = """
var out = [];
try {
  var jw = window.jwplayer && window.jwplayer();
  if (jw && jw.getPlaylistItem) {
    (jw.getPlaylistItem().allSources || jw.getPlaylistItem().sources || []).forEach(function(s) {
      if (s.file && !s.file.startsWith('blob:')) out.push(s.file);
    });
  }
} catch(e) {}
try {
  if (window.Hls && window.hls && window.hls.url) out.push(window.hls.url);
} catch(e) {}
try {
  if (window.videojs) {
    Object.values(videojs.getPlayers ? videojs.getPlayers() : {}).forEach(function(p) {
      var src = p.currentSrc && p.currentSrc();
      if (src && !src.startsWith('blob:')) out.push(src);
    });
  }
} catch(e) {}
return out.concat(window.__captured_media || []);
"""


@register_tool('www_find_dl')
class FindDownloadLinkTool(BaseTool):
    description = (
        'Find media download links (video, image, audio, HLS/m3u8) in a page by URL. '
        'Scans HTML tags and inline script blocks. '
        'Use js=true for pages that load the player via JavaScript. '
        'Use click_play=true when the player only fetches the stream URL after the play button is clicked (blob: URL pages).'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url':          {'type': 'string', 'description': 'URL of the page to search for media links.'},
            'js':           {'type': 'boolean', 'description': 'Use headless Firefox to execute JavaScript first. Default: false.'},
            'click_play':   {'type': 'boolean', 'description': 'After page load, inject a network intercept then click the play button to trigger the stream URL fetch. Requires js=true.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load (and after click if click_play=true). Default: 3.'},
            'cookies':      {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional cookies in "name=value" format.'},
            'referrer':     {'type': 'string', 'description': 'Referer header to send with the page request.'},
        },
        'required': ['url'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url          = p.get('url', '')
        js           = p.get('js', False)
        click_play   = p.get('click_play', False)
        wait_seconds = max(1, min(30, p.get('wait_seconds', 3)))
        cookies      = p.get('cookies', None)
        referrer     = p.get('referrer', '')

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        player_links = []

        try:
            if js:
                from selenium.webdriver.common.by import By
                driver = _get_or_create_browser()
                if cookies:
                    from urllib.parse import urlparse as _up
                    driver.get(f"{_up(url).scheme}://{_up(url).netloc}")
                    time.sleep(1)
                    for c in cookies:
                        if '=' in c:
                            name, _, value = c.partition('=')
                            driver.add_cookie({'name': name.strip(), 'value': value.strip(), 'domain': _up(url).netloc})
                driver.get(url)
                time.sleep(wait_seconds)

                if click_play:
                    driver.execute_script(_INTERCEPT_JS)
                    for sel in _PLAY_SELECTORS:
                        try:
                            btn = driver.find_element(By.CSS_SELECTOR, sel)
                            btn.click()
                            break
                        except Exception:
                            continue
                    time.sleep(wait_seconds)

                raw_results = driver.execute_script(_PLAYER_EXTRACT_JS) or []
                origin = urllib.parse.urlparse(url)
                base = f"{origin.scheme}://{origin.netloc}"
                player_links = [
                    {'tag': 'player', 'src': src if src.startswith('http') else base + src}
                    for src in dict.fromkeys(raw_results)
                    if src
                ]
                raw_html = driver.page_source
            else:
                session_headers = { 'Referer': referrer } if referrer else {}
                _apply_cookies(url, cookies, None)
                r = _web_session.get(url, timeout=15, headers=session_headers)
                r.raise_for_status()
                raw_html = r.text
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

        script_links = [
            {'tag': 'script', 'src': match}
            for match in dict.fromkeys( _MEDIA_URL_RE.findall(raw_html) )
        ]

        try:
            soup = beautifulsoup.BeautifulSoup(_strip_html_noise(raw_html), 'html.parser')
        except Exception as e:
            return tool_result(error=f"HTML parsing failed: {e}")

        tag_links = []
        for tag_name in ('video', 'source', 'img', 'audio'):
            for el in soup.find_all(tag_name):
                src = el.get('src') or el.get('data-src') or ''
                if src and not src.startswith('blob:'):
                    tag_links.append({'tag': tag_name, 'src': src})

        links = player_links + script_links + tag_links
        return tool_result(data={'url': url, 'links': links, 'count': len(links)})


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


def _fetch_with_headers(url: str, headers: dict, retries: int = 5) -> requests.Response:
    delay = 2.0
    for attempt in range(retries):
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get('Retry-After', delay))
            time.sleep(wait)
            delay = min(delay * 2, 60)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Still getting 429 after {retries} retries: {url}")


def _run_hls_download(job_id: str, url: str, dest: str, headers: dict) -> None:
    import tempfile
    try:
        if dest.lower().endswith('.m3u8'):
            dest = dest[:-5] + '.mp4'
            with _dl_lock:
                _dl_jobs[job_id]['dest'] = dest

        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)

        # Try yt-dlp first — battle-tested rate-limit + retry handling for HLS
        ytdlp = shutil.which('yt-dlp')
        if ytdlp:
            cmd = [
                ytdlp, '--no-warnings', '--quiet',
                '--sleep-interval', '1', '--max-sleep-interval', '3',
                '--retries', '10', '--fragment-retries', '10',
                '-o', dest,
            ]
            for k, v in headers.items():
                cmd += ['--add-header', f'{k}:{v}']
            cmd.append(url)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(dest):
                size = os.path.getsize(dest)
                with _dl_lock:
                    _dl_jobs[job_id].update({'status': 'done', 'bytes_done': size})
                return
            # yt-dlp failed — fall through to manual
            ytdlp_err = (result.stderr or result.stdout)[-400:]
        else:
            ytdlp_err = 'yt-dlp not found'

        # Manual fallback: requests playlist fetch + per-segment download + ffmpeg concat
        r = _fetch_with_headers(url, headers)
        playlist = r.text
        base_url = url.rsplit('/', 1)[0] + '/'
        segments = [
            line.strip() if line.strip().startswith('http') else base_url + line.strip()
            for line in playlist.splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        if not segments:
            raise RuntimeError(f"No segments in playlist (yt-dlp also failed: {ytdlp_err})")

        written = 0
        with tempfile.TemporaryDirectory() as tmp:
            seg_paths = []
            for idx, seg_url in enumerate(segments):
                seg_path = os.path.join(tmp, f"seg{idx:05d}.ts")
                seg_data = _fetch_with_headers(seg_url, headers).content
                with open(seg_path, 'wb') as sf:
                    sf.write(seg_data)
                seg_paths.append(seg_path)
                written += len(seg_data)
                with _dl_lock:
                    _dl_jobs[job_id]['bytes_done'] = written
                if idx < len(segments) - 1:
                    time.sleep(0.5)

            concat_file = os.path.join(tmp, 'concat.txt')
            with open(concat_file, 'w') as cf:
                cf.write('\n'.join( f"file '{p}'" for p in seg_paths ))
            cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', concat_file, '-c', 'copy', dest]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[-800:] or result.stdout[-400:])

        size = os.path.getsize(dest)
        with _dl_lock:
            _dl_jobs[job_id].update({'status': 'done', 'bytes_done': size})
    except Exception as e:
        with _dl_lock:
            _dl_jobs[job_id].update({'status': 'error', 'error': str(e)})


@register_tool('www_dl')
class DownloadFileTool(BaseTool):
    description = (
        'Download a file from a direct URL to disk. '
        'The url must be a direct link to the file — if you only have a page URL, '
        'call www_find_dl first to extract the real download link. '
        'IMPORTANT: CDN-signed URLs (e.g. HLS/m3u8 with key= tokens) expire within minutes — '
        'always call www_find_dl immediately before www_dl, never reuse a URL from earlier in context. '
        'Returns a job_id immediately — download runs in the background. '
        'Use www_dl_status to check progress. '
        'Pass wait=true to block until the download finishes.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url':        {'type': 'string', 'description': 'Direct URL to the file.'},
            'dest':       {'type': 'string', 'description': 'Local file path or directory. Filename is derived from URL when a directory is given.'},
            'media_type': {'type': 'string', 'description': 'Type of file being downloaded: video/movie/film, image/photo/photograph, document/text, binary/executable/code/script.'},
            'wait':       {'type': 'boolean', 'description': 'Block until download completes. Default false.'},
            'headers':    {'type': 'object', 'description': 'Optional HTTP headers (e.g. User-Agent, Referer). Required for CDN-protected HLS streams.'},
            'referrer':   {'type': 'string', 'description': 'Shorthand for setting the Referer header. Merged into headers if both are provided.'},
        },
        'required': ['url', 'dest', 'media_type'],
    }

    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url        = p['url']
        dest       = os.path.expanduser(p['dest'])
        media_type = p.get('media_type', '')
        wait       = p.get('wait', False)
        headers    = dict(p.get('headers') or {})
        referrer   = p.get('referrer', '')
        if referrer:
            headers.setdefault('Referer', referrer)

        err = _validate_url(url)
        if err:
            return tool_result(error=err)

        media_type = _MEDIA_TYPE_ALIASES.get(media_type, media_type)
        if media_type not in _MEDIA_EXTS:
            return tool_result(error=(
                f"media_type must be one of: {', '.join(_MEDIA_EXTS)} "
                f"(or aliases: photo, photograph, movie, film, executable, script, etc.)."
            ))

        exts = _MEDIA_EXTS[media_type]
        url_path = url.lower().split('?')[0].rstrip('/')
        url_qs   = url.lower().split('?')[1] if '?' in url else ''
        qs_has_m3u8 = 'm3u8' in url_qs
        if not any(url_path.endswith(ext) for ext in exts) and not qs_has_m3u8:
            return tool_result(error=(
                f"'{url}' does not look like a direct {media_type} link "
                f"(expected one of: {', '.join(exts[:6])}...). "
                "Call www_find_dl on the page URL first to extract the real download link, "
                "then pass that to www_dl."
            ))

        if os.path.isdir(dest):
            filename = os.path.basename(urllib.parse.urlparse(url).path) or 'download'
            dest = os.path.join(dest, filename)

        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)

        job_id = uuid.uuid4().hex[:8]
        with _dl_lock:
            _dl_jobs[job_id] = {'url': url, 'dest': dest, 'status': 'running', 'bytes_done': 0, 'total_bytes': 0}

        is_hls = url_path.endswith('.m3u8') or qs_has_m3u8
        future = (
            _dl_executor.submit(_run_hls_download, job_id, url, dest, headers)
            if is_hls else
            _dl_executor.submit(_run_download, job_id, url, dest)
        )

        if wait:
            future.result()
            with _dl_lock:
                job = dict(_dl_jobs[job_id])
            if job['status'] == 'error':
                return tool_result(error=job['error'])
            return tool_result(data={'job_id': job_id, 'status': 'done', 'path': job.get('dest', dest), 'bytes': job['bytes_done']})

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
        'Queries the DOM of a given site to return CSS selectors for use in creating site structure templates.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'URL of a gallery/listing page to analyze.'},
            'js': {'type': 'boolean', 'description': 'Use headless browser for JS-rendered pages. Default false.'},
            'wait_seconds': {'type': 'integer', 'description': 'Seconds to wait after JS load. Default 3.'},
            'min_cards': {'type': 'integer', 'description': 'Minimum repetitions to consider a candidate card element. Default 5.'},
            'click': {'type': 'string', 'description': 'CSS selector of an element to click after page load (e.g. cookie banner dismiss, load-more button). Requires js=true.'},
            'save': {'type': 'boolean', 'description': 'Save the best card structure to known_site_structures.json for future reuse. Default false.'},
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
        save = bool(p.get('save', False))

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

            # Media wrapper group: the majority of sampled instances must contain
            # both a link and at least one media element (thumbnail or preview_video).
            # This distinguishes gallery cards from nav menus, footers, etc.
            media_count = sum(
                1 for s in scores
                if 'link' in s and ('thumbnail' in s or 'preview_video' in s)
            )
            if media_count < max(1, len(scores) * 0.5):
                continue

            avg_fields = sum(len(s) for s in scores) / len(scores)
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
                'media_confirmed': media_count,
            })

        candidates.sort(key=lambda c: (-c['media_confirmed'], -c['field_count'], -c['count']))
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
            c.pop('media_confirmed', None)

        # Optionally persist the best structure for future fetches on this site.
        saved = False
        if save and top:
            parsed_origin = urllib.parse.urlparse(url)
            origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
            entry = {
                'url': origin,
                'container': container_selector,
                'cards': [{'selector': top[0]['selector'], 'fields': top[0]['fields']}],
            }
            _KNOWN_SITES_PATH.parent.mkdir(parents=True, exist_ok=True)
            sites = _load_tube_site_selectors()
            updated = False
            for idx, existing in enumerate(sites):
                if _match_site_by_url(origin, [existing]):
                    sites[idx] = entry
                    updated = True
                    break
            if not updated:
                sites.append(entry)
            with open(_KNOWN_SITES_PATH, 'w') as f:
                json.dump(sites, f, indent=2)
            saved = True

        return tool_result(data={
            'url': url,
            'container': container_selector,
            'card_candidates': top,
            **({"saved_to": str(_KNOWN_SITES_PATH)} if saved else {}),
        })


_PAGINATION_CONTAINERS = ["pagination", "pagination-container", "pagination-wrapper"]

