"""Web tools: search and fetch URLs."""

import os
import re
import json
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path

from langchain.tools import tool

from credentials import build_auth_headers, list_credentials as _list_creds, get_credential

# ── Image storage ────────────────────────────────────────────────────────────
_IMAGE_DIR = Path(__file__).resolve().parent.parent / "static" / "images"
_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


# ── Web Operations ───────────────────────────────────────────────────────────

@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results.

    Args:
        query: Search query string.
        num_results: Max results to return.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"ERROR: DuckDuckGo search failed: {e}"

    results = []
    if data.get("AbstractText"):
        results.append(f"[Answer] {data['AbstractText']}\n  Source: {data.get('AbstractURL', 'N/A')}")
    for topic in data.get("RelatedTopics", [])[:num_results]:
        if isinstance(topic, dict) and "Text" in topic:
            results.append(f"[Result] {topic['Text']}\n  URL: {topic.get('FirstURL', 'N/A')}")
    if not results:
        return f"No instant answer found for: {query}\nTry: https://duckduckgo.com/?q={encoded}"
    return "\n\n".join(results)


@tool
def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch a URL and return its text content (HTML tags stripped).

    Args:
        url: URL to fetch.
        max_chars: Maximum characters to return.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: Failed to fetch {url}: {e}"

    if "html" in content_type.lower() or raw.strip().startswith("<"):
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()

    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n... (truncated at {max_chars} chars)"
    return raw


@tool
def download_image(url: str, filename: str = "") -> str:
    """Download an image from a URL to local storage and return a local path for display.

    The image is saved to static/images/ and can be displayed in chat via the
    returned local URL path. Supports jpg, jpeg, png, gif, webp, svg.

    Args:
        url: Direct URL to the image file.
        filename: Optional filename to save as. Auto-generated from URL hash if empty.
    """
    ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

    # Determine extension from URL
    parsed = urllib.parse.urlparse(url)
    url_path = parsed.path.lower()
    ext = os.path.splitext(url_path)[1]
    if ext not in ALLOWED_EXT:
        ext = ".jpg"  # default fallback

    if not filename:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
        filename = f"{url_hash}{ext}"
    elif not os.path.splitext(filename)[1]:
        filename = f"{filename}{ext}"

    dest = _IMAGE_DIR / filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if not any(t in content_type for t in ["image/", "octet-stream"]):
                return f"ERROR: URL does not appear to be an image (Content-Type: {content_type})"
            data = resp.read()
            if len(data) > 20 * 1024 * 1024:
                return "ERROR: Image exceeds 20MB limit"
            dest.write_bytes(data)
    except Exception as e:
        return f"ERROR: Failed to download image: {e}"

    size_kb = len(data) / 1024
    return json.dumps({
        "status": "ok",
        "local_path": f"/static/images/{filename}",
        "filename": filename,
        "size_kb": round(size_kb, 1),
        "display": f"![{filename}](/static/images/{filename})",
    })


# ── Authenticated requests ────────────────────────────────────────────────────

@tool
def list_saved_credentials() -> str:
    """List all saved credential aliases and their types.

    Shows which sites have stored credentials available for authenticated requests.
    Secrets are masked — only aliases, types, and URLs are shown.
    """
    creds = _list_creds()
    if not creds:
        return "No saved credentials. Add them with: python credentials.py add <alias> --url <url> --username <user> --password <pass>"

    lines = ["Saved credentials:\n"]
    for c in creds:
        detail = f"  {c['alias']:20s}  [{c['type']}]  {c['url']}"
        if c.get("username"):
            detail += f"  user: {c['username']}"
        lines.append(detail)
    return "\n".join(lines)


@tool
def authenticated_fetch(credential_alias: str, path: str = "", method: str = "GET",
                        body: str = "", max_chars: int = 5000) -> str:
    """Fetch a URL using stored credentials for authentication.

    The base URL comes from the credential, and the path is appended to it.
    Use list_saved_credentials first to see available aliases.

    Args:
        credential_alias: Alias of the stored credential to use.
        path: Path to append to the credential's base URL (e.g. "/api/v1/items").
        method: HTTP method — GET, POST, PUT, DELETE.
        body: Request body for POST/PUT (sent as-is with Content-Type: application/json).
        max_chars: Maximum characters to return from the response.
    """
    cred = get_credential(credential_alias)
    if not cred:
        return f"ERROR: No credential found for '{credential_alias}'. Use list_saved_credentials to see available aliases."

    base_url = cred.get("url", "").rstrip("/")
    if path:
        url = base_url + "/" + path.lstrip("/")
    else:
        url = base_url

    try:
        auth_headers = build_auth_headers(credential_alias)
    except Exception as e:
        return f"ERROR: Could not build auth headers: {e}"

    headers = {"User-Agent": "AgentTooling/1.0"}
    headers.update(auth_headers)

    data = None
    if method in ("POST", "PUT") and body:
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json"

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500] if e.fp else ""
        return f"ERROR: HTTP {e.code} {e.reason}\n{body_text}"
    except Exception as e:
        return f"ERROR: Request failed: {e}"

    # Strip HTML if needed
    if "html" in content_type.lower() or raw.strip().startswith("<"):
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()

    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n... (truncated at {max_chars} chars)"

    return f"[{status}] {url}\n{raw}"


@tool
def authenticated_post_form(credential_alias: str, path: str = "",
                            form_data: str = "", max_chars: int = 5000) -> str:
    """Submit a form using stored credentials (application/x-www-form-urlencoded).

    Args:
        credential_alias: Alias of the stored credential to use.
        path: Path to append to the credential's base URL.
        form_data: URL-encoded form data (e.g. "field1=value1&field2=value2").
        max_chars: Maximum characters to return from the response.
    """
    cred = get_credential(credential_alias)
    if not cred:
        return f"ERROR: No credential found for '{credential_alias}'."

    base_url = cred.get("url", "").rstrip("/")
    url = base_url + "/" + path.lstrip("/") if path else base_url

    try:
        auth_headers = build_auth_headers(credential_alias)
    except Exception as e:
        return f"ERROR: Could not build auth headers: {e}"

    headers = {"User-Agent": "AgentTooling/1.0", "Content-Type": "application/x-www-form-urlencoded"}
    headers.update(auth_headers)

    data = form_data.encode("utf-8") if form_data else b""

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")[:500] if e.fp else ""
        return f"ERROR: HTTP {e.code} {e.reason}\n{body_text}"
    except Exception as e:
        return f"ERROR: Request failed: {e}"

    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n... (truncated at {max_chars} chars)"

    return f"[{status}] {url}\n{raw}"


WEB_TOOLS = [web_search, fetch_url, download_image, list_saved_credentials, authenticated_fetch, authenticated_post_form]
