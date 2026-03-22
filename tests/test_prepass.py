"""Tests for tool pre-pass module."""

import json
import pytest


# --- Compact index ---

def test_build_compact_index():
    """Compact index extracts name + first line of description."""
    from prepass import _build_compact_index

    full_tools = [
        {"name": "read", "description": "Read a file and return its contents.\nSupports text and binary.", "params": {}},
        {"name": "web_search", "description": "Search the web using DuckDuckGo", "params": {}},
    ]
    index = _build_compact_index(full_tools)
    assert index == {
        "read": "Read a file and return its contents.",
        "web_search": "Search the web using DuckDuckGo",
    }


def test_build_compact_index_empty():
    from prepass import _build_compact_index
    assert _build_compact_index([]) == {}


def test_build_compact_index_missing_description():
    from prepass import _build_compact_index
    tools = [{"name": "foo", "description": "", "params": {}}]
    index = _build_compact_index(tools)
    assert index == {"foo": ""}


# --- Pre-pass prompt ---

def test_build_prepass_prompt():
    from prepass import _build_prepass_prompt

    index = {"read": "Read a file", "web_search": "Search the web"}
    prompt = _build_prepass_prompt("find me a recipe", index)
    assert "find me a recipe" in prompt
    assert "read: Read a file" in prompt
    assert "web_search: Search the web" in prompt
    assert "JSON array" in prompt


# --- Parse pre-pass response ---

def test_parse_prepass_response_valid():
    from prepass import _parse_prepass_response
    known = {"read", "web_search", "ls"}
    result = _parse_prepass_response('["read", "web_search"]', known)
    assert result == ["read", "web_search"]


def test_parse_prepass_response_filters_unknown():
    from prepass import _parse_prepass_response
    known = {"read", "ls"}
    result = _parse_prepass_response('["read", "nonexistent"]', known)
    assert result == ["read"]


def test_parse_prepass_response_malformed_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response("not json at all", {"read"})
    assert result is None


def test_parse_prepass_response_empty_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response("[]", {"read"})
    assert result is None


def test_parse_prepass_response_all_unknown_returns_none():
    from prepass import _parse_prepass_response
    result = _parse_prepass_response('["fake1", "fake2"]', {"read"})
    assert result is None


def test_parse_prepass_response_strips_think_tags():
    """qwen3 models wrap output in <think>...</think> tags."""
    from prepass import _parse_prepass_response
    known = {"read", "web_search"}
    raw = '<think>\nThe user wants to read a file.\n</think>\n["read"]'
    result = _parse_prepass_response(raw, known)
    assert result == ["read"]
