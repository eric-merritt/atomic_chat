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

def test_find_download_link_no_url_returns_error():
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


# ── Functional test: DownloadFileTool validation ─────────────────────────────

import tempfile

def test_dl_missing_media_type_returns_error():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/file.mp4", "dest": tempfile.gettempdir()}))
    assert result["status"] == "error"
    assert "media_type" in result["error"]

def test_dl_invalid_media_type_returns_error():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/file.mp4", "dest": tempfile.gettempdir(), "media_type": "banana"}))
    assert result["status"] == "error"
    assert "media_type" in result["error"]

def test_dl_video_page_url_tells_agent_to_use_find_dl():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/watch?v=abc123", "dest": tempfile.gettempdir(), "media_type": "video"}))
    assert result["status"] == "error"
    assert "www_find_dl" in result["error"]

def test_dl_image_page_url_tells_agent_to_use_find_dl():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/gallery/photo", "dest": tempfile.gettempdir(), "media_type": "image"}))
    assert result["status"] == "error"
    assert "www_find_dl" in result["error"]

def test_dl_document_page_url_tells_agent_to_use_find_dl():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/reports/annual", "dest": tempfile.gettempdir(), "media_type": "document"}))
    assert result["status"] == "error"
    assert "www_find_dl" in result["error"]

def test_dl_accepts_valid_video_url():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/video.mp4", "dest": tempfile.gettempdir(), "media_type": "video"}))
    # passes validation — will fail on network, not on extension check
    assert "www_find_dl" not in result.get("error", "")

def test_dl_accepts_valid_image_url():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/photo.jpg", "dest": tempfile.gettempdir(), "media_type": "image"}))
    assert "www_find_dl" not in result.get("error", "")

def test_dl_accepts_valid_document_url():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/report.pdf", "dest": tempfile.gettempdir(), "media_type": "document"}))
    assert "www_find_dl" not in result.get("error", "")

def test_dl_accepts_valid_binary_url():
    from tools.web import DownloadFileTool
    tool = DownloadFileTool()
    result = tool.call(json.dumps({"url": "https://example.com/setup.exe", "dest": tempfile.gettempdir(), "media_type": "binary"}))
    assert "www_find_dl" not in result.get("error", "")


# ── Functional test: FindAllowedRoutesTool validation ────────────────────────

def test_find_allowed_routes_bad_url_returns_error():
    from tools.web import FindAllowedRoutesTool

    tool = FindAllowedRoutesTool()
    result = tool.call(json.dumps({"url": "ftp://bad"}))
    assert result["status"] == "error"
