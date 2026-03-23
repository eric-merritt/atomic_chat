"""Tests for Task Extractor prompt building and response parsing."""
from task_extractor import _build_extractor_prompt, _parse_extractor_response


class TestBuildPrompt:
    def test_includes_user_message(self):
        prompt = _build_extractor_prompt("scrape the site", [], [])
        assert "scrape the site" in prompt

    def test_includes_existing_tasks(self):
        tasks = [{"title": "existing task", "status": "pending"}]
        prompt = _build_extractor_prompt("do more", tasks, [])
        assert "existing task" in prompt

    def test_includes_recent_messages(self):
        history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        prompt = _build_extractor_prompt("next step", [], history)
        assert "hello" in prompt

    def test_empty_tasks_shows_none(self):
        prompt = _build_extractor_prompt("hi", [], [])
        assert "(none)" in prompt


class TestParseResponse:
    def test_valid_array(self):
        result = _parse_extractor_response('["task one", "task two"]')
        assert result == ["task one", "task two"]

    def test_empty_array(self):
        result = _parse_extractor_response('[]')
        assert result == []

    def test_with_think_tags(self):
        raw = '<think>hmm let me think</think>["scrape URL"]'
        result = _parse_extractor_response(raw)
        assert result == ["scrape URL"]

    def test_malformed_returns_empty(self):
        result = _parse_extractor_response("I don't understand")
        assert result == []

    def test_non_string_items_filtered(self):
        result = _parse_extractor_response('[123, "valid task", null]')
        assert result == ["valid task"]

    def test_json_in_surrounding_text(self):
        raw = 'Here are the tasks: ["task A"] hope that helps'
        result = _parse_extractor_response(raw)
        assert result == ["task A"]
