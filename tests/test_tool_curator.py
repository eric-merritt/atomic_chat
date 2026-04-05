"""Tests for Tool Curator prompt building and response parsing."""

import json

from pipeline.tool_curator import (
    _build_curator_prompt,
    _parse_curator_response,
    TaskToolMapping,
)
from pipeline.workflow_groups import WORKFLOW_GROUPS


# ---------------------------------------------------------------------------
# _build_curator_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_includes_task_titles(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "scrape a website", "status": "pending"}],
            user_tool_names=[],
        )
        assert "scrape a website" in prompt

    def test_includes_multiple_tasks_in_order(self):
        prompt = _build_curator_prompt(
            tasks=[
                {"title": "first task", "status": "pending"},
                {"title": "second task", "status": "in_progress"},
            ],
            user_tool_names=[],
        )
        assert "1. [pending] first task" in prompt
        assert "2. [in_progress] second task" in prompt

    def test_includes_all_workflow_group_names(self):
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=[],
        )
        for name in WORKFLOW_GROUPS:
            assert name in prompt, f"Group '{name}' missing from prompt"

    def test_active_groups_shown_when_user_has_tools(self):
        # Pick the first group and grab one of its tools
        first_group = next(iter(WORKFLOW_GROUPS))
        first_tool = WORKFLOW_GROUPS[first_group].tools[0]
        prompt = _build_curator_prompt(
            tasks=[{"title": "task", "status": "pending"}],
            user_tool_names=[first_tool],
        )
        assert first_group in prompt


# ---------------------------------------------------------------------------
# _parse_curator_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    TASKS = [
        {"title": "scrape prices", "status": "pending"},
        {"title": "write report", "status": "pending"},
    ]

    def test_valid_json_array(self):
        raw = json.dumps([
            {"task": 1, "tool": "mcp"},
            {"task": 2, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 2
        assert mappings[0].task_title == "scrape prices"
        assert mappings[0].tool == "mcp"
        assert mappings[1].task_title == "write report"

    def test_think_tags_stripped(self):
        raw = '<think>let me think about this</think>' + json.dumps([
            {"task": 1, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].task_title == "scrape prices"

    def test_multiline_think_tags(self):
        raw = "<think>\nlong\nthought\nprocess\n</think>\n" + json.dumps([
            {"task": 2, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].task_title == "write report"

    def test_malformed_returns_empty(self):
        mappings = _parse_curator_response("gibberish no json here", self.TASKS)
        assert mappings == []

    def test_empty_string_returns_empty(self):
        mappings = _parse_curator_response("", self.TASKS)
        assert mappings == []

    def test_invalid_task_number_skipped(self):
        raw = json.dumps([
            {"task": 999, "tool": "mcp"},
            {"task": 1, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].task_title == "scrape prices"

    def test_unknown_tool_falls_back_to_mcp(self):
        raw = json.dumps([
            {"task": 1, "tool": "nonexistent_tool_xyz"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].tool == "mcp"

    def test_missing_tool_field_skipped(self):
        raw = json.dumps([
            {"task": 1},
            {"task": 2, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].task_title == "write report"

    def test_non_dict_items_skipped(self):
        raw = json.dumps([
            "not a dict",
            {"task": 1, "tool": "mcp"},
        ])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1

    def test_known_tool_gets_group(self):
        # Find a real tool from WORKFLOW_GROUPS
        first_group = next(iter(WORKFLOW_GROUPS))
        first_tool = WORKFLOW_GROUPS[first_group].tools[0]
        raw = json.dumps([{"task": 1, "tool": first_tool}])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].group == first_group

    def test_mcp_tool_has_no_group(self):
        raw = json.dumps([{"task": 1, "tool": "mcp"}])
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
        assert mappings[0].group is None

    def test_json_embedded_in_text(self):
        raw = 'Here is my analysis:\n[{"task": 1, "tool": "mcp"}]\nDone.'
        mappings = _parse_curator_response(raw, self.TASKS)
        assert len(mappings) == 1
