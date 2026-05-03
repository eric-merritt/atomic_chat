"""Tests for web tools converted to qwen-agent BaseTool."""

import json
import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration tests ───────────────────────────────────────────────────────

def test_all_web_tools_registered():
    import tools.web  # noqa: F401 — trigger registration

    expected = {
        'www_ddg',
        'www_find_content',
        'www_find_dl',
        'www_dl',
        'www_dl_status',
        'www_find_routes',
        'www_query',
        'www_click',
        'www_find_struct',
        'www_set_cookies',
        'www_set_local_storage',
        'www_get_cookies',
        'www_get_cookies_for_url',
    }
    registered = set(TOOL_REGISTRY.keys())
    missing = expected - registered
    assert not missing, f"Missing from TOOL_REGISTRY: {missing}"


def test_ddg_search_registered():
    import tools.web  # noqa: F401
    assert 'www_ddg' in TOOL_REGISTRY


def test_find_download_link_registered():
    import tools.web  # noqa: F401
    assert 'www_find_dl' in TOOL_REGISTRY


def test_find_allowed_routes_registered():
    import tools.web  # noqa: F401
    assert 'www_find_routes' in TOOL_REGISTRY


def test_browser_query_registered():
    import tools.web  # noqa: F401
    assert 'www_query' in TOOL_REGISTRY


def test_browser_click_registered():
    import tools.web  # noqa: F401
    assert 'www_click' in TOOL_REGISTRY


# ── Class identity tests ─────────────────────────────────────────────────────

def test_tool_classes_are_base_tool_subclasses():
    from qwen_agent.tools.base import BaseTool
    import tools.web  # noqa: F401

    tool_names = [
        'www_ddg', 'www_find_content', 'www_find_dl', 'www_dl',
        'www_dl_status', 'www_find_routes', 'www_query', 'www_click',
        'www_find_struct',
    ]
    for name in tool_names:
        cls = TOOL_REGISTRY[name]
        assert issubclass(cls, BaseTool), f"{name} is not a BaseTool subclass"


# ── Functional test: FindDownloadLinkTool ────────────────────────────────────

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


# ── Functional test: WebSearchTool (www_ddg) validation ──────────────────────

def test_ddg_search_empty_query_returns_error():
    from tools.web import WebSearchTool

    tool = WebSearchTool()
    result = tool.call(json.dumps({"query": ""}))
    assert result["status"] == "error"
    assert "query" in result["error"]


# ── Functional test: FindAllowedRoutesTool validation ────────────────────────

def test_find_allowed_routes_bad_url_returns_error():
    from tools.web import FindAllowedRoutesTool

    tool = FindAllowedRoutesTool()
    result = tool.call(json.dumps({"url": "ftp://bad"}))
    assert result["status"] == "error"
