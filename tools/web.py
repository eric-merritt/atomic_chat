"""Web tools: search and fetch URLs."""

import re
import json
import urllib.request
import urllib.parse
import bs4 as beautifulsoup
import typing

import requests

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



@tool
def webscrape(url):
    """
    A tool that goes to a webpage and copies its HTML content.


    Args:
      url: The webpage to gather the HTML content from.agents
    """

    r = requests.get(url)
    return r

@tool
def find_all(html: str, target: str):
    """
    A tool that breaks up HTML code into individual pieces.
    """
    soup = beautifulsoup(html, 'html.parser')
    return soup.find_all(target)

@tool
def find_download_link(html = "", url = ""):
    """
    A tool that parses HTML for download links.
    """
    media_elements = ['video','source','img']
    found = []
    if html != "":
        for el in media_elements:
            soup = beautifulsoup(html, "html.parser")
            found.push(soup.find_all(el))

    if url != "":
        html = webscrape(url)
        find_download_link(html = html, url = "")

    soup = beautifulsoup(found.join(), 'html.parser')
    links = []
    for el in media_elements:
        if el.startswith('<source'):
            if el.src.endswith('mp4'):
                links.push(el.src)

    return links

@tool
def find_allowed_routes(url):
    """
    A tool that returns the allowed paths from a website's robot.txt file.


    Args:
      url: The url of the website to scrape the allowed crawl paths from.
    """
    if not url.endswith('robots.txt'):
        url = url + 'robots.txt'

    html = webscrape(url)
    lines = html.split("\n")
    allowed = []
    for line in lines:
        if line.startswith('Allow: '):
            allowed.push(line)
    return allowed



WEB_TOOLS = [web_search, fetch_url, webscrape, find_all, find_download_link, find_allowed_routes]
