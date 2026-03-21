# Tool Registry Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor all 45 tools across 8 files to be deterministic, schema-driven, safe, and optimized for weaker instruction-following LLMs (Qwen2.5-Coder, abliterated variants).

**Architecture:** Each tool returns a standardized JSON string `{"status": "success"|"error", "data": ..., "error": ""}`. Unsafe auth patterns are replaced with session/cookie-based auth. Magic values (`-1`) become `Optional[int] = None`. All tools get strict, literal docstrings.

**Tech Stack:** Python, LangChain `@tool` decorator, Selenium WebDriver, qBittorrent Web API, BeautifulSoup, urllib/requests.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/web.py` | **Rewrite** | Fix .push() bugs, fix webscrape return type, standardize output |
| `tools/onlyfans.py` | **Rewrite** | Remove credential params, require session cookies, standardize output |
| `tools/torrent.py` | **Modify** | Eliminate global `_last_search_results`, standardize output |
| `tools/marketplace.py` | **Modify** | Replace `-1` magic values with `None`, standardize output, improve docstrings |
| `tools/filesystem.py` | **Modify** | Fix write() pkexec bug, standardize output, add side-effect warnings |
| `tools/codesearch.py` | **Modify** | Standardize output, remove `pattern` alias ambiguity |
| `tools/mcp.py` | **Rewrite** | Add type hints, standardize output |
| `tools/pagenav.py` | **No action** | Internal helper functions (not registered as tools). Not imported in `__init__.py`. Contains `find_page_nav`, `extract_pages`, `get_page_links` — pagination helpers used by marketplace scrapers. Out of scope for this refactor because they are not `@tool`-decorated and not in any tool registry. Last line has dead code (`PAGE_NAVIGATION_TOOLS` defined inside unreachable indentation). |
| `tools/__init__.py` | **Modify** | Add torrent tools import (currently missing) |
| `tools/_output.py` | **Create** | Shared `tool_result()` helper for standardized JSON output |

### Naming Normalization Audit

Reviewed all tool names against spec requirement 7. Decisions:

| Current Name | Verdict | Rationale |
|---|---|---|
| `webscrape` | **Rename → `fetch_html`** | Aligns with `fetch_url` pattern; "scrape" is ambiguous |
| `find_all` | **Keep** | Mirrors BeautifulSoup API; familiar to Python developers |
| `find_download_link` | **Keep** | Self-explanatory, no abbreviations |
| `find_allowed_routes` | **Keep** | Clear intent |
| `connect_to_mcp` | **Keep** | Self-explanatory |
| `get_OF_cookies` | **Remove** | Being removed for security reasons (Task 3) |
| `login_to_onlyfans` | **Remove** | Being removed for security reasons (Task 3) |
| All filesystem/codesearch/marketplace/torrent tools | **Keep** | Already self-explanatory with consistent patterns |

The `webscrape` → `fetch_html` rename is applied in Task 2.

### Files Explicitly Out of Scope

- `tools/pagenav.py` — internal helpers, not tool-registered
- `tools/fix.py` — untracked WIP file
- `tools_server.py` — untracked, separate server entry point

---

## Task 1: Create Shared Output Helper

**Files:**
- Create: `tools/_output.py`

This is the foundation — every subsequent task depends on this helper.

- [ ] **Step 1: Create `tools/_output.py`**

```python
"""Standardized tool output format."""

import json


def tool_result(data=None, error: str = "") -> str:
    """Return a standardized JSON response string.

    All tools MUST return the output of this function.

    Args:
        data: The tool's result payload. Can be any JSON-serializable value.
        error: Error message string. If non-empty, status is "error".

    Returns:
        JSON string: {"status": "success"|"error", "data": ..., "error": ""}
    """
    if error:
        return json.dumps({"status": "error", "data": None, "error": error})
    return json.dumps({"status": "success", "data": data, "error": ""})
```

- [ ] **Step 2: Verify the file is importable**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools._output import tool_result; print(tool_result(data='test'))"`

Expected: `{"status": "success", "data": "test", "error": ""}`

- [ ] **Step 3: Commit**

```bash
git add tools/_output.py
git commit -m "feat: add standardized tool output helper"
```

---

## Task 2: Fix and Refactor `tools/web.py` (PRIORITY: Critical Bugs)

**Files:**
- Modify: `tools/web.py` (all 6 tools — lines 1-141)

**Problems:**
1. `webscrape` returns `requests.Response` object instead of `str`
2. `find_all` returns non-serializable `Tag` objects
3. `find_download_link` uses `.push()` (JavaScript, not Python), `.join()` on list, `.startswith()` on Tag
4. `find_allowed_routes` uses `.push()` on list
5. No type hints on `webscrape`, `find_all`, `find_download_link`, `find_allowed_routes`
6. No standardized output format
7. Weak docstrings

- [ ] **Step 1: Rewrite `web_search`**

Add standardized output, keep existing logic. Add strict docstring.

```python
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
```

- [ ] **Step 2: Rewrite `fetch_url`**

```python
@tool
def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch a URL and return its text content with HTML tags stripped.

    WHEN TO USE: When you need to read the text content of a specific webpage.
    WHEN NOT TO USE: When you need raw HTML (use webscrape instead).

    Args:
        url: Full URL to fetch. Must start with http:// or https://.
        max_chars: Maximum characters to return. Range: 100-50000.

    Output format:
        {"status": "success", "data": {"url": "...", "content": "...", "truncated": false}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
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
```

- [ ] **Step 3: Fix and rewrite `webscrape`**

The original returns a `requests.Response` object. Fix to return HTML string.

```python
@tool
def webscrape(url: str) -> str:
    """Fetch a URL and return the raw HTML content.

    WHEN TO USE: When you need the raw HTML of a webpage for parsing with find_all or find_download_link.
    WHEN NOT TO USE: When you need readable text content (use fetch_url instead).

    Args:
        url: Full URL to fetch. Must start with http:// or https://.

    Output format:
        {"status": "success", "data": {"url": "...", "html": "..."}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "AgentTooling/1.0"})
        r.raise_for_status()
    except Exception as e:
        return tool_result(error=f"Failed to fetch {url}: {e}")

    return tool_result(data={"url": url, "html": r.text})
```

- [ ] **Step 4: Fix and rewrite `find_all`**

The original returns BeautifulSoup Tag objects (not serializable). Fix to return list of strings.

```python
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
```

- [ ] **Step 5: Fix and rewrite `find_download_link`**

The original is entirely broken (.push(), .join() on list, .startswith() on Tag). Rewrite from scratch.

```python
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
```

- [ ] **Step 6: Fix and rewrite `find_allowed_routes`**

The original uses `.push()` on list and calls `webscrape` which returns Response object.

```python
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
```

- [ ] **Step 7: Update imports and WEB_TOOLS list**

Update the top of the file:

```python
"""Web tools: search and fetch URLs."""

import re
import json
import urllib.request
import urllib.parse

import bs4 as beautifulsoup
import requests

from langchain.tools import tool
from tools._output import tool_result
```

Remove the `typing` import (unused). Keep the WEB_TOOLS list the same.

- [ ] **Step 8: Verify web tools are importable**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.web import WEB_TOOLS; print(f'{len(WEB_TOOLS)} web tools loaded')"`

Expected: `6 web tools loaded`

- [ ] **Step 9: Commit**

```bash
git add tools/web.py
git commit -m "fix: rewrite web tools — fix .push() bugs, standardize output, add type hints"
```

---

## Task 3: Refactor `tools/onlyfans.py` (PRIORITY: Security)

**Files:**
- Modify: `tools/onlyfans.py` (all 8 tools — lines 1-330)

**Problems:**
1. `login_to_onlyfans` and `get_OF_cookies` accept raw email/password
2. Tools return `None`, `WebDriver`, or `list` instead of `str`
3. No standardized output format
4. Hardcoded geckodriver path

**Strategy:** Replace credential-based login with cookie/session-based auth. All tools that need a driver now require it to be pre-authenticated. Remove `login_to_onlyfans` and `get_OF_cookies` as @tool functions — keep as internal helpers with explicit warnings.

- [ ] **Step 1: Remove `login_to_onlyfans` and `get_OF_cookies` from tool registry**

These tools accept raw credentials and automate login. Replace with a session-cookie-based approach.

Rewrite `login_to_onlyfans` as a private helper `_create_driver_from_cookies`:

```python
def _create_driver_from_cookies(cookies: list[dict], geckodriver_path: str = "") -> webdriver.Firefox:
    """Create an authenticated Firefox driver from pre-obtained cookies.

    DO NOT pass raw credentials to this function.
    Cookies should be obtained manually or from a secure credential store.

    Args:
        cookies: List of cookie dicts with keys: name, value, domain, path.
        geckodriver_path: Path to geckodriver binary. Auto-detected if empty.
    """
    if not geckodriver_path:
        geckodriver_path = os.environ.get("GECKODRIVER_PATH", "/home/ermer/.local/bin/geckodriver")

    firefox_options = Options()
    firefox_options.accept_insecure_certs = True

    service = Service(geckodriver_path)
    driver = webdriver.Firefox(service=service, options=firefox_options)

    driver.get("https://onlyfans.com")
    time.sleep(2)

    for cookie in cookies:
        driver.add_cookie(cookie)

    driver.get(MESSAGES_PAGE)
    time.sleep(2)

    return driver
```

- [ ] **Step 2: Add module-level driver management**

Since WebDriver objects can't be serialized to JSON, all OnlyFans tools operate on a module-level `_active_driver` reference. This is set by calling `_create_driver_from_cookies()` during session setup (not by the LLM directly).

Add at module level:
```python
_active_driver: webdriver.Firefox | None = None

def _get_driver() -> webdriver.Firefox:
    """Get the active driver session. Raises if not initialized."""
    if _active_driver is None:
        raise RuntimeError(
            "No active OnlyFans session. Call _create_driver_from_cookies() first."
        )
    return _active_driver
```

- [ ] **Step 3: Rewrite all 6 tools with standardized output**

Remove the `driver` parameter from all tools — they use `_get_driver()` internally. The LLM never passes a driver; it just calls the tool.

```python
@tool("scroll_conversations")
@retry()
def scroll_conversations() -> str:
    """Scroll the OnlyFans conversations sidebar until all conversations are loaded.

    WHEN TO USE: Before iterating through conversations to ensure all are loaded.
    WHEN NOT TO USE: When you only need the currently visible conversations.

    REQUIRES: An active OnlyFans session (set up before calling this tool).
    SIDE EFFECT: Modifies the scroll position of the conversation sidebar in the browser.

    WARNING: DO NOT pass raw credentials (email/password) to any tool.
    Use pre-obtained session cookies for authentication.

    Output format:
        {"status": "success", "data": {"message": "Scrolled to end of conversations"}, "error": ""}
    """
    try:
        driver = _get_driver()
        scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)
        last_height = 0
        while True:
            driver.execute_script(
                "arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroller
            )
            time.sleep(2)
            new_height = scroller.size["height"]
            if new_height == last_height:
                break
            last_height = new_height
        return tool_result(data={"message": "Scrolled to end of conversations"})
    except Exception as e:
        return tool_result(error=str(e))


@tool("scroll_messages")
@retry()
def scroll_messages() -> str:
    """Scroll the current conversation to load additional messages.

    WHEN TO USE: When you need to load older messages in the current conversation.
    WHEN NOT TO USE: When you are not inside a conversation view.

    REQUIRES: An active OnlyFans session with a conversation open.
    SIDE EFFECT: Scrolls the message container, triggering lazy loading of older messages.

    WARNING: DO NOT pass raw credentials (email/password) to any tool.

    Output format:
        {"status": "success", "data": {"message": "Scrolled message container"}, "error": ""}
    """
    try:
        driver = _get_driver()
        scroller = driver.find_element(By.CLASS_NAME, SCROLLER_CLASS)
        driver.execute_script(
            "arguments[0].scrollTo(0, arguments[0].scrollHeight);", scroller
        )
        time.sleep(2)
        return tool_result(data={"message": "Scrolled message container"})
    except Exception as e:
        return tool_result(error=str(e))


@tool("save_image")
@retry()
def save_image(url: str, file_path: str) -> str:
    """Download and save an image from a URL to disk.

    WHEN TO USE: When you have a direct image URL to download.
    WHEN NOT TO USE: When you need to find image URLs first (use extract_images_and_videos).

    WARNING: This WRITES a file to disk. Verify the save path before calling.

    Args:
        url: Direct image URL. Must start with http:// or https://.
        file_path: Local file path to save the image to.

    Output format:
        {"status": "success", "data": {"url": "...", "file_path": "...", "bytes": N}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(r.content)
        return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
    except Exception as e:
        return tool_result(error=str(e))


@tool("save_video")
@retry()
def save_video(url: str, file_path: str) -> str:
    """Download and save a video from a URL to disk.

    WHEN TO USE: When you have a direct video URL to download.
    WHEN NOT TO USE: When you need to find video URLs first (use extract_images_and_videos).

    WARNING: This WRITES a file to disk. Verify the save path before calling.

    Args:
        url: Direct video URL. Must start with http:// or https://.
        file_path: Local file path to save the video to.

    Output format:
        {"status": "success", "data": {"url": "...", "file_path": "...", "bytes": N}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(r.content)
        return tool_result(data={"url": url, "file_path": file_path, "bytes": len(r.content)})
    except Exception as e:
        return tool_result(error=str(e))


@tool("extract_images_and_videos")
@retry()
def extract_images_and_videos(save_dir: str) -> str:
    """Extract all images and videos from the currently open conversation.

    WHEN TO USE: When inside a conversation and you want to download all media.
    WHEN NOT TO USE: When you want to extract from ALL conversations (use extract_media).

    REQUIRES: An active OnlyFans session with a conversation open.
    SIDE EFFECT: Downloads files to save_dir. Scrolls the conversation to load all messages.

    WARNING: DO NOT pass raw credentials. This tool writes multiple files to disk.

    Args:
        save_dir: Directory path where media files will be saved. Created if it does not exist.

    Output format:
        {"status": "success", "data": {"save_dir": "...", "images_saved": N, "videos_saved": N}, "error": ""}
    """
    try:
        driver = _get_driver()
        os.makedirs(save_dir, exist_ok=True)
        images_saved = 0
        videos_saved = 0

        while True:
            scroll_messages.invoke({})
            messages = driver.find_elements(By.CLASS_NAME, MESSAGE_CLASS)
            for msg_i, message in enumerate(messages):
                try:
                    media_wrapper = safe_find(message, By.CLASS_NAME, MEDIA_WRAPPER_CLASS)
                    if not media_wrapper:
                        continue
                    for i, img in enumerate(media_wrapper.find_elements(By.CLASS_NAME, IMAGE_CLASS)):
                        src = img.get_attribute("src")
                        if src:
                            save_image.invoke({"url": src, "file_path": f"{save_dir}/image_{msg_i}_{i}.jpg"})
                            images_saved += 1
                    for i, video in enumerate(media_wrapper.find_elements(By.CLASS_NAME, VIDEO_CLASS)):
                        for j, source in enumerate(video.find_elements(By.TAG_NAME, "source")):
                            src = source.get_attribute(SOURCE_ATTRIBUTE)
                            if src:
                                save_video.invoke({"url": src, "file_path": f"{save_dir}/video_{msg_i}_{i}_{j}.mp4"})
                                videos_saved += 1
                except Exception:
                    continue
            try:
                status = driver.find_element(By.CSS_SELECTOR, INFINITE_STATUS_PROMPT_CLASS)
                if "hidden" in status.get_attribute("class"):
                    break
            except Exception:
                break

        return tool_result(data={"save_dir": save_dir, "images_saved": images_saved, "videos_saved": videos_saved})
    except Exception as e:
        return tool_result(error=str(e))


@tool("extract_media")
@retry()
def extract_media(save_dir: str) -> str:
    """Extract media from ALL conversations in the user's OnlyFans inbox.

    WHEN TO USE: When you want to download all media from all conversations.
    WHEN NOT TO USE: When you only need media from the current conversation (use extract_images_and_videos).

    REQUIRES: An active OnlyFans session.
    SIDE EFFECT: Navigates through all conversations, downloads all media to save_dir.
    This is a long-running operation that clicks through every conversation.

    WARNING: DO NOT pass raw credentials. This tool writes many files to disk.

    Args:
        save_dir: Directory to store downloaded media. Created if it does not exist.

    Output format:
        {"status": "success", "data": {"save_dir": "...", "conversations_processed": N, "conversations_failed": N}, "error": ""}
    """
    try:
        driver = _get_driver()
        os.makedirs(save_dir, exist_ok=True)
        driver.get(MESSAGES_PAGE)
        time.sleep(2)
        scroll_conversations.invoke({})
        conversations = driver.find_elements(By.CLASS_NAME, CONVERSATION_CLASS)
        processed = 0
        failed = 0
        for i, conversation in enumerate(conversations):
            try:
                conversation.click()
                time.sleep(1)
                extract_images_and_videos.invoke({"save_dir": save_dir})
                processed += 1
            except Exception:
                failed += 1
                continue
        return tool_result(data={"save_dir": save_dir, "conversations_processed": processed, "conversations_failed": failed})
    except Exception as e:
        return tool_result(error=str(e))
```

- [ ] **Step 4: Add credential warning to module docstring**

Add at the top of the file:
```python
"""OnlyFans media extraction tools.

WARNING: These tools require an active authenticated session created from
pre-obtained cookies. DO NOT pass raw credentials (email/password) to any tool.
"""
```

- [ ] **Step 5: Update ONLYFANS_TOOLS registry**

Remove `login_to_onlyfans` and `get_OF_cookies` from the exported list:

```python
ONLYFANS_TOOLS = [
    extract_media,
    extract_images_and_videos,
    scroll_conversations,
    scroll_messages,
    save_image,
    save_video,
]
```

- [ ] **Step 6: Add import for tool_result**

```python
from tools._output import tool_result
```

- [ ] **Step 7: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.onlyfans import ONLYFANS_TOOLS; print(f'{len(ONLYFANS_TOOLS)} onlyfans tools loaded')"`

Expected: `6 onlyfans tools loaded`

- [ ] **Step 8: Commit**

```bash
git add tools/onlyfans.py
git commit -m "security: remove credential-based login tools, require session cookies"
```

---

## Task 4: Refactor `tools/torrent.py` (PRIORITY: Global State Leak)

**Files:**
- Modify: `tools/torrent.py` (lines 1-347)

**Problems:**
1. `_last_search_results` is module-level global — leaks between users/sessions
2. `_authenticated` and `_cookie_jar` are global — same issue
3. No standardized output format
4. `torrent_download` silently depends on prior `torrent_search` call

**Strategy:** Replace global `_last_search_results` with search results embedded in the output of `torrent_search`, so `torrent_download` takes URLs directly instead of indices. Keep `_cookie_jar` and `_authenticated` as module-level (acceptable for single-user CLI), but document the limitation.

- [ ] **Step 1: Add import for tool_result**

```python
from tools._output import tool_result
```

- [ ] **Step 2: Rewrite `torrent_search` to embed download URLs in output**

Instead of caching results in a global, return them so the LLM can pass URLs to `torrent_add` directly.

Key changes:
- Return `tool_result(data={"results": [...], "count": N})`
- Each result includes `"download_url"` field
- Remove `_last_search_results.clear()` / `.extend()`
- Add instructions in output: "Use torrent_add with the download_url to start downloading."

```python
@tool
def torrent_search(query: str, plugins: str = "all", category: str = "all", max_results: int = 20) -> str:
    """Search for torrents using qBittorrent's search plugins.

    WHEN TO USE: When you need to find torrents by keyword.
    WHEN NOT TO USE: When you already have a magnet link or torrent URL (use torrent_add instead).

    Starts a search, waits for completion, and returns results sorted by seeders.
    Each result includes a download_url. Pass these to torrent_add to download.

    Args:
        query: Search terms. Must be non-empty.
        plugins: Plugin to use. "all" for all enabled, or a specific plugin name.
        category: Category filter. "all", "movies", "tv", "music", "games", "software".
        max_results: Maximum number of results to return. Range: 1-100.

    Output format:
        {"status": "success", "data": {"query": "...", "count": N, "results": [
            {"name": "...", "size": "...", "seeders": N, "leechers": N, "ratio": "...", "site": "...", "download_url": "..."},
            ...
        ]}, "error": ""}
    """
```

- [ ] **Step 3: Rewrite `torrent_download` to accept URLs directly**

Remove dependency on `_last_search_results`. Instead, accept URLs directly.

```python
@tool
def torrent_download(urls: str, category: str = "", paused: bool = False) -> str:
    """Download torrents by URL or magnet link.

    WHEN TO USE: After torrent_search, pass the download_url values from search results.
    WHEN NOT TO USE: When you don't have specific URLs yet (use torrent_search first).

    This is an alias for torrent_add. Kept for backward compatibility.

    Args:
        urls: Magnet links or torrent URLs, one per line or separated by |.
        category: Optional category to assign (e.g. "movies", "linux-isos").
        paused: If true, add in paused state instead of starting immediately.

    Output format:
        {"status": "success", "data": {"added": N, "urls": [...]}, "error": ""}
    """
    return torrent_add.invoke({"urls": urls, "category": category, "paused": paused})
```

- [ ] **Step 4: Remove the `_last_search_results` global**

Delete lines 18-19:
```python
# Cache last search results so torrent_download can reference by index
_last_search_results: list[dict] = []
```

- [ ] **Step 5: Standardize output for remaining tools**

Update `torrent_list_plugins`, `torrent_enable_plugin`, `torrent_add`, `torrent_list_active` to use `tool_result()`.

- [ ] **Step 6: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.torrent import TORRENT_TOOLS; print(f'{len(TORRENT_TOOLS)} torrent tools loaded')"`

Expected: `6 torrent tools loaded`

- [ ] **Step 7: Commit**

```bash
git add tools/torrent.py
git commit -m "fix: remove global state leak in torrent tools, standardize output"
```

---

## Task 5: Refactor `tools/marketplace.py` — Replace Magic Values

**Files:**
- Modify: `tools/marketplace.py` (lines 137-770, tool signatures and docstrings)

**Problems:**
1. `min_price: float = -1` and `max_price: float = -1` are magic sentinel values
2. Docstrings say "-1 to skip" which is implicit
3. LLM might pass `-1` thinking it means something

**Strategy:** Replace `-1` defaults with `Optional[float] = None`. Update all internal logic to check `is not None` instead of `>= 0`.

- [ ] **Step 1: Add imports**

```python
from typing import Optional
from tools._output import tool_result
```

- [ ] **Step 2: Update `ebay_search` signature and logic**

Change:
```python
def ebay_search(
    query: str,
    sort: str = "best_match",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    condition: str = "",
    max_results: int = 20,
) -> str:
```

Change internal logic from `if min_price >= 0:` to `if min_price is not None:`.

- [ ] **Step 3: Update all other marketplace tool signatures**

Apply the same `Optional[float] = None` / `Optional[int] = None` pattern to:
- `ebay_deep_scan` (min_price, max_price)
- `amazon_search` (min_price, max_price)
- `craigslist_search` (min_price, max_price)
- `craigslist_multi_search` (min_price, max_price)
- `cross_platform_search` (min_price, max_price)
- `deal_finder` (min_price, max_price)
- `_craigslist_search_city` helper (min_price, max_price)

- [ ] **Step 4: Standardize output format**

Wrap all tool returns with `tool_result()`. Replace:
```python
return json.dumps(listings, indent=2)
```
With:
```python
return tool_result(data={"query": query, "count": len(listings), "listings": listings})
```

And replace error returns:
```python
return json.dumps([{"error": str(e)}])
```
With:
```python
return tool_result(error=str(e))
```

- [ ] **Step 5: Add strict docstrings to all 9 tools**

Each docstring must include WHEN TO USE, WHEN NOT TO USE, exact Args, and Output format sections. Example for `ebay_search`:

```python
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
```

- [ ] **Step 6: Document flow tool pipelines (Spec Requirement 3)**

For each flow tool, add an explicit `PIPELINE STEPS` section to its docstring. This satisfies Option A from the spec (keep as single tool but explicitly document internal pipeline).

For `cross_platform_search`:
```python
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
        {"status": "success", "data": {"query": "...", "platforms_searched": [...], "total_listings": N, "results": {"ebay": [...], "amazon": [...], "craigslist": [...]}}, "error": ""}
    """
```

For `deal_finder`:
```python
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
        {"status": "success", "data": {"query": "...", "total_listings_analyzed": N, "group_statistics": {...}, "deals_found": N, "deals": [{"model": "...", "total_cost": N, "median_price": N, "pct_below_median": N, "url": "..."}]}, "error": ""}
    """
```

For `enrichment_pipeline`:
```python
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
```

For `craigslist_multi_search` (also a looping tool):
```python
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
```

- [ ] **Step 7: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.marketplace import MARKETPLACE_TOOLS, FLOW_TOOLS; print(f'{len(MARKETPLACE_TOOLS)} marketplace, {len(FLOW_TOOLS)} flow tools loaded')"`

Expected: `6 marketplace, 3 flow tools loaded`

- [ ] **Step 8: Commit**

```bash
git add tools/marketplace.py
git commit -m "refactor: replace magic -1 values with Optional[None], document flow pipelines, standardize output"
```

---

## Task 6: Refactor `tools/filesystem.py` — Side Effects & Output

**Files:**
- Modify: `tools/filesystem.py` (lines 1-279)

**Problems:**
1. `write()` has incomplete pkexec fallback (creates dir but never writes file)
2. `delete()` has confusing dual-mode API (start=0,end=0 deletes file vs line range)
3. No standardized output format
4. No warnings about destructive/irreversible operations
5. Weak docstrings for LLM consumption

- [ ] **Step 1: Add import for tool_result**

```python
from tools._output import tool_result
```

- [ ] **Step 2: Fix `write()` pkexec bug**

Replace lines 120-128:
```python
@tool
def write(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    WHEN TO USE: When you need to create a new file or overwrite an existing file entirely.
    WHEN NOT TO USE: When you need to modify part of a file (use replace or insert instead).

    WARNING: This is a DESTRUCTIVE operation. It OVERWRITES the entire file content.
    Any existing content in the file will be permanently lost.

    Args:
        path: Absolute or relative file path.
        content: Full file content to write.

    Output format:
        {"status": "success", "data": {"path": "/abs/path", "bytes_written": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            written = f.write(content)
        return tool_result(data={"path": os.path.abspath(path), "bytes_written": written})
    except PermissionError:
        return tool_result(error=f"Permission denied: {os.path.abspath(path)}")
```

- [ ] **Step 3: Add destructive-operation warnings to `delete`, `move`**

For `delete`:
```python
    """Delete a file, empty directory, or a range of lines from a file.

    WARNING: File/directory deletion is IRREVERSIBLE. Deleted files cannot be recovered.
    Line deletion modifies the file in place.

    ...
    """
```

For `move`:
```python
    """Move or rename a file or directory.

    WARNING: If the destination already exists, it will be OVERWRITTEN.

    ...
    """
```

- [ ] **Step 4: Standardize output for all 12 tools**

Replace plain string returns with `tool_result()` calls. Examples:
- `read`: `return tool_result(data={"path": path, "content": "\n".join(numbered)})`
- `info`: `return tool_result(data=info_dict)`
- `ls`: `return tool_result(data={"path": path, "entries": entries})`
- `delete`: `return tool_result(data={"path": path, "action": "deleted_file"|"deleted_lines", ...})`

- [ ] **Step 5: Add strict docstrings to all 12 tools**

Each must include WHEN TO USE, WHEN NOT TO USE, Args, Output format, and WARNING for destructive operations.

- [ ] **Step 6: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.filesystem import FILESYSTEM_TOOLS; print(f'{len(FILESYSTEM_TOOLS)} filesystem tools loaded')"`

Expected: `12 filesystem tools loaded`

- [ ] **Step 7: Commit**

```bash
git add tools/filesystem.py
git commit -m "fix: fix write() pkexec bug, add destructive-op warnings, standardize output"
```

---

## Task 7: Refactor `tools/codesearch.py` — Clarity & Output

**Files:**
- Modify: `tools/codesearch.py` (lines 1-136)

**Problems:**
1. `find` has confusing `name` vs `pattern` alias
2. No standardized output format
3. Weak docstrings

- [ ] **Step 1: Add import for tool_result**

```python
from tools._output import tool_result
```

- [ ] **Step 2: Remove `pattern` alias from `find`**

Remove the `pattern` parameter. If backward compatibility is needed, keep it but mark clearly:

```python
@tool
def find(
    path: str = ".",
    name: str = "",
    extension: str = "",
    contains: str = "",
    max_results: int = 50,
) -> str:
    """Find files by name pattern, extension, or content.

    WHEN TO USE: When you need to locate files by name, extension, or content.
    WHEN NOT TO USE: When you need to search file CONTENTS with regex (use grep instead).

    Args:
        path: Directory to search. Defaults to current directory.
        name: Glob pattern for filename (e.g. "test_*", "*.py"). If empty, matches all files.
        extension: File extension filter (e.g. ".py", "py"). Do not combine with name.
        contains: Only return files containing this exact string.
        max_results: Maximum files to return. Range: 1-500.

    Output format:
        {"status": "success", "data": {"path": "...", "count": N, "files": [...]}, "error": ""}
    """
```

- [ ] **Step 3: Standardize output for all 3 tools**

- [ ] **Step 4: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.codesearch import CODESEARCH_TOOLS; print(f'{len(CODESEARCH_TOOLS)} codesearch tools loaded')"`

Expected: `3 codesearch tools loaded`

- [ ] **Step 5: Commit**

```bash
git add tools/codesearch.py
git commit -m "refactor: remove ambiguous pattern alias, standardize output in codesearch tools"
```

---

## Task 8: Refactor `tools/mcp.py` — Type Hints & Output

**Files:**
- Modify: `tools/mcp.py` (lines 1-16)

**Problems:**
1. No type hints
2. Returns `dict` or `str` (inconsistent)
3. No error handling beyond status code
4. Minimal docstring

- [ ] **Step 1: Rewrite `connect_to_mcp`**

```python
"""MCP tools: connect to Model Context Protocol servers."""

import json
import requests
from langchain.tools import tool
from tools._output import tool_result


@tool("connect_to_mcp")
def connect_to_mcp(url: str) -> str:
    """Connect to an MCP server and retrieve its available tools.

    WHEN TO USE: When you need to discover tools available on an MCP server.
    WHEN NOT TO USE: When you already know which tools are available.

    Args:
        url: Full URL of the MCP server endpoint. Must start with http:// or https://.

    Output format:
        {"status": "success", "data": {"url": "...", "tools": [...]}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        return tool_result(error=f"Response from {url} is not valid JSON")
    except Exception as e:
        return tool_result(error=f"Failed to connect to MCP server: {e}")

    return tool_result(data={"url": url, "tools": data})


MCP_TOOLS = [connect_to_mcp]
```

- [ ] **Step 2: Verify imports**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools.mcp import MCP_TOOLS; print(f'{len(MCP_TOOLS)} mcp tools loaded')"`

Expected: `1 mcp tools loaded`

- [ ] **Step 3: Commit**

```bash
git add tools/mcp.py
git commit -m "refactor: add type hints and standardized output to MCP tool"
```

---

## Task 9: Fix `tools/__init__.py` — Add Missing Torrent Import

**Files:**
- Modify: `tools/__init__.py` (lines 1-11)

**Problem:** Torrent tools are not exported in `ALL_TOOLS`.

- [ ] **Step 1: Add torrent import**

```python
"""Tool registry — grouped by agent domain."""

from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS, FLOW_TOOLS
from tools.onlyfans import ONLYFANS_TOOLS
from tools.torrent import TORRENT_TOOLS
from tools.mcp import MCP_TOOLS

ALL_TOOLS = (
    FILESYSTEM_TOOLS
    + CODESEARCH_TOOLS
    + WEB_TOOLS
    + MARKETPLACE_TOOLS
    + FLOW_TOOLS
    + ONLYFANS_TOOLS
    + TORRENT_TOOLS
    + MCP_TOOLS
)
```

- [ ] **Step 2: Verify full registry**

Run: `cd /home/ermer/devproj/python/agentic_w_langchain_ollama && python -c "from tools import ALL_TOOLS; print(f'{len(ALL_TOOLS)} total tools loaded'); [print(f'  - {t.name}') for t in ALL_TOOLS]"`

Expected: All tools listed, no import errors.

- [ ] **Step 3: Commit**

```bash
git add tools/__init__.py
git commit -m "fix: add missing torrent tools to ALL_TOOLS registry"
```

---

## Execution Order & Dependencies

```
Task 1 (_output.py)
  ├─→ Task 2 (web.py)         — critical bugs
  ├─→ Task 3 (onlyfans.py)    — security
  ├─→ Task 4 (torrent.py)     — global state
  ├─→ Task 5 (marketplace.py) — magic values
  ├─→ Task 6 (filesystem.py)  — pkexec bug
  ├─→ Task 7 (codesearch.py)  — clarity
  └─→ Task 8 (mcp.py)         — type hints
         └─→ Task 9 (__init__.py) — depends on all above
```

Tasks 2-8 are independent of each other (all depend only on Task 1). Task 9 must be last.
