"""Tests for web tools converted to qwen-agent BaseTool."""

import json
import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration tests ───────────────────────────────────────────────────────

def test_all_web_tools_registered():
    """All 10 web tools must be present in the qwen-agent TOOL_REGISTRY."""
    import tools.web  # noqa: F401 — trigger registration

    expected = {
        'web_search',
        'www_fetch',
        'www_scrape',
        'www_cookies',
        'www_find_all',
        'www_find_dl',
        'www_find_routes',
        'www_browse',
        'www_query',
        'www_click',
    }
    registered = set(TOOL_REGISTRY.keys())
    missing = expected - registered
    assert not missing, f"Missing from TOOL_REGISTRY: {missing}"


def test_web_search_registered():
    import tools.web  # noqa: F401
    assert 'web_search' in TOOL_REGISTRY


def test_fetch_url_registered():
    import tools.web  # noqa: F401
    assert 'www_fetch' in TOOL_REGISTRY


def test_webscrape_registered():
    import tools.web  # noqa: F401
    assert 'www_scrape' in TOOL_REGISTRY


def test_find_all_registered():
    import tools.web  # noqa: F401
    assert 'www_find_all' in TOOL_REGISTRY


def test_find_download_link_registered():
    import tools.web  # noqa: F401
    assert 'www_find_dl' in TOOL_REGISTRY


def test_find_allowed_routes_registered():
    import tools.web  # noqa: F401
    assert 'www_find_routes' in TOOL_REGISTRY


def test_browser_fetch_registered():
    import tools.web  # noqa: F401
    assert 'www_browse' in TOOL_REGISTRY


def test_browser_query_registered():
    import tools.web  # noqa: F401
    assert 'www_query' in TOOL_REGISTRY


def test_browser_click_registered():
    import tools.web  # noqa: F401
    assert 'www_click' in TOOL_REGISTRY


# ── Class identity tests ─────────────────────────────────────────────────────

def test_tool_classes_are_base_tool_subclasses():
    """Each registered tool class must be a BaseTool subclass."""
    from qwen_agent.tools.base import BaseTool
    import tools.web  # noqa: F401

    tool_names = [
        'web_search', 'www_fetch', 'www_scrape', 'www_find_all',
        'www_find_dl', 'www_find_routes',
        'www_browse', 'www_query', 'www_click',
    ]
    for name in tool_names:
        cls = TOOL_REGISTRY[name]
        assert issubclass(cls, BaseTool), f"{name} is not a BaseTool subclass"


# ── Functional test: FindAllTool HTML parsing ────────────────────────────────

def test_find_all_css_selector():
    """FindAllTool must parse HTML and return matching elements via CSS selector."""
    from tools.web import FindAllTool

    html = """
    <html><body>
        <div class="card"><a href="/one">Link 1</a></div>
        <div class="card"><a href="/two">Link 2</a></div>
        <div class="other"><a href="/three">Link 3</a></div>
    </body></html>
    """
    tool = FindAllTool()
    result = tool.call(json.dumps({"html": html, "target": "div.card > a"}))

    assert result["status"] == "success"
    assert result["data"]["count"] == 2
    assert result["data"]["target"] == "div.card > a"
    elements = result["data"]["elements"]
    assert any("/one" in el for el in elements)
    assert any("/two" in el for el in elements)
    assert not any("/three" in el for el in elements)


def test_find_all_plain_tag():
    """FindAllTool must select plain tag names (not just CSS selectors)."""
    from tools.web import FindAllTool

    html = "<ul><li>A</li><li>B</li><li>C</li></ul>"
    tool = FindAllTool()
    result = tool.call(json.dumps({"html": html, "target": "li"}))

    assert result["status"] == "success"
    assert result["data"]["count"] == 3


def test_find_all_empty_html_returns_error():
    from tools.web import FindAllTool

    tool = FindAllTool()
    result = tool.call(json.dumps({"html": "", "target": "a"}))
    assert result["status"] == "error"
    assert "html" in result["error"]


def test_find_all_empty_target_returns_error():
    from tools.web import FindAllTool

    tool = FindAllTool()
    result = tool.call(json.dumps({"html": "<p>hi</p>", "target": ""}))
    assert result["status"] == "error"
    assert "target" in result["error"]


def test_find_all_no_matches():
    """FindAllTool must return count=0 and empty list when selector matches nothing."""
    from tools.web import FindAllTool

    tool = FindAllTool()
    result = tool.call(json.dumps({"html": "<p>hello</p>", "target": "div.nonexistent"}))
    assert result["status"] == "success"
    assert result["data"]["count"] == 0
    assert result["data"]["elements"] == []


# ── Functional test: FindDownloadLinkTool ───────────────────────────────────

def test_find_download_link_from_html():
    from tools.web import FindDownloadLinkTool

    html = """
    <video src="/media/video.mp4"></video>
    <img src="/media/thumb.jpg" />
    <audio src="/media/audio.mp3"></audio>
    """
    tool = FindDownloadLinkTool()
    result = tool.call(json.dumps({"html": html}))

    assert result["status"] == "success"
    links = result["data"]["links"]
    tags = {l["tag"] for l in links}
    assert "video" in tags
    assert "img" in tags
    assert "audio" in tags


def test_find_download_link_no_input_returns_error():
    from tools.web import FindDownloadLinkTool

    tool = FindDownloadLinkTool()
    result = tool.call(json.dumps({}))
    assert result["status"] == "error"


# ── Functional test: web_search validation ───────────────────────────────────

def test_web_search_empty_query_returns_error():
    from tools.web import WebSearchTool

    tool = WebSearchTool()
    result = tool.call(json.dumps({"query": ""}))
    assert result["status"] == "error"
    assert "query" in result["error"]


# ── Functional test: fetch_url validation ───────────────────────────────────

def test_fetch_url_bad_url_returns_error():
    from tools.web import FetchUrlTool

    tool = FetchUrlTool()
    result = tool.call(json.dumps({"url": "not-a-url"}))
    assert result["status"] == "error"
    assert "http" in result["error"]


# ── Functional test: find_allowed_routes validation ──────────────────────────

def test_find_allowed_routes_bad_url_returns_error():
    from tools.web import FindAllowedRoutesTool

    tool = FindAllowedRoutesTool()
    result = tool.call(json.dumps({"url": "ftp://bad"}))
    assert result["status"] == "error"
