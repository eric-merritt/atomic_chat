"""Web tools: search and fetch URLs."""

import re
import json
import urllib.request
import urllib.parse

from langchain.tools import tool


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


WEB_TOOLS = [web_search, fetch_url]
