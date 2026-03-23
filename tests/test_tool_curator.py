"""Tests for Tool Curator prompt building, response parsing, and short-circuit."""
from tool_curator import (
    _build_curator_prompt,
    _parse_curator_response,
    CurationResult,
)
from workflow_groups import WORKFLOW_GROUPS


class TestBuildPrompt:
    def test_includes_tasks(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "scrape a website", "status": "pending"}],
            user_tool_names=["read", "write"],
        )
        assert "scrape a website" in prompt

    def test_includes_user_tools(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=["read", "write"],
        )
        assert "read" in prompt
        assert "write" in prompt

    def test_includes_workflow_groups(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=[],
        )
        for name in WORKFLOW_GROUPS:
            assert name in prompt


class TestParseResponse:
    def test_pass_action(self):
        result = _parse_curator_response('{"action": "pass"}')
        assert result == CurationResult(action="pass", groups=[], reason="")

    def test_recommend_action(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Web Tools"], "reason": "Aids with scraping"}'
        )
        assert result.action == "recommend"
        assert result.groups == ["Web Tools"]
        assert result.reason == "Aids with scraping"

    def test_unknown_group_filtered(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Web Tools", "Fake Group"], "reason": "test"}'
        )
        assert result.groups == ["Web Tools"]

    def test_all_groups_invalid_becomes_pass(self):
        result = _parse_curator_response(
            '{"action": "recommend", "groups": ["Nonexistent"], "reason": "test"}'
        )
        assert result.action == "pass"

    def test_malformed_returns_pass(self):
        result = _parse_curator_response("gibberish")
        assert result.action == "pass"

    def test_with_think_tags(self):
        raw = '<think>analyzing</think>{"action": "recommend", "groups": ["Accounting"], "reason": "Needs bookkeeping"}'
        result = _parse_curator_response(raw)
        assert result.action == "recommend"
        assert result.groups == ["Accounting"]
