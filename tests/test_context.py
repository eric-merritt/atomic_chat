"""Tests for context pipeline module (qwen-agent dict format)."""

import pytest


# --- Message conversion ---

def test_user_message_conversion():
    from context import _db_row_to_qwen

    row = {"role": "user", "content": "hello", "tool_calls": []}
    msg = _db_row_to_qwen(row)
    assert msg == {"role": "user", "content": "hello"}


def test_assistant_message_conversion():
    from context import _db_row_to_qwen

    row = {"role": "assistant", "content": "hi there", "tool_calls": []}
    msg = _db_row_to_qwen(row)
    assert msg == {"role": "assistant", "content": "hi there"}


def test_tool_result_conversion():
    from context import _db_row_to_qwen

    row = {
        "role": "tool",
        "content": '{"status": "success", "data": "file contents"}',
        "tool_calls": [{"name": "read", "id": "call_1"}],
    }
    msg = _db_row_to_qwen(row)
    assert msg["role"] == "function"
    assert msg["name"] == "read"
    assert msg["content"] == '{"status": "success", "data": "file contents"}'


def test_tool_result_missing_tool_calls():
    from context import _db_row_to_qwen

    row = {"role": "tool", "content": "some output", "tool_calls": []}
    msg = _db_row_to_qwen(row)
    assert msg["role"] == "function"
    assert msg["name"] == "unknown"


def test_unknown_role_falls_back_to_user():
    from context import _db_row_to_qwen

    row = {"role": "system", "content": "sys prompt", "tool_calls": []}
    msg = _db_row_to_qwen(row)
    assert msg == {"role": "user", "content": "sys prompt"}


# --- Truncation ---

def test_tool_result_truncation():
    from context import _db_row_to_qwen

    long_content = "x" * 5000
    row = {"role": "tool", "content": long_content, "tool_calls": [{"name": "www_ddg", "id": "call_2"}]}
    msg = _db_row_to_qwen(row)
    assert len(msg["content"]) == 4000


# --- Build history ---

def test_build_history_ordering():
    from context import build_history

    db_messages = [
        {"role": "user", "content": "first", "tool_calls": []},
        {"role": "assistant", "content": "response1", "tool_calls": []},
        {"role": "user", "content": "second", "tool_calls": []},
    ]
    history = build_history(db_messages)
    assert len(history) == 3
    assert history[0] == {"role": "user", "content": "first"}
    assert history[1] == {"role": "assistant", "content": "response1"}
    assert history[2] == {"role": "user", "content": "second"}


def test_build_history_empty():
    from context import build_history
    assert build_history([]) == []


def test_build_history_with_tool_message():
    from context import build_history

    db_messages = [
        {"role": "user", "content": "search for cats", "tool_calls": []},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "www_ddg", "args": {"q": "cats"}, "id": "c1"}]},
        {"role": "tool", "content": "results here", "tool_calls": [{"name": "www_ddg", "id": "c1"}]},
    ]
    history = build_history(db_messages)
    assert history[2] == {"role": "function", "name": "www_ddg", "content": "results here"}


# --- Serialization for DB ---

def test_serialize_user_message():
    from context import serialize_user_message

    row = serialize_user_message("what is 2+2")
    assert row == {"role": "user", "content": "what is 2+2", "tool_calls": []}


def test_serialize_assistant_text():
    from context import serialize_assistant_message

    row = serialize_assistant_message("The answer is 4", tool_calls=[])
    assert row == {"role": "assistant", "content": "The answer is 4", "tool_calls": []}


def test_serialize_assistant_with_none_tool_calls():
    from context import serialize_assistant_message

    row = serialize_assistant_message("text", tool_calls=None)
    assert row["tool_calls"] == []


def test_serialize_assistant_tool_call():
    from context import serialize_assistant_message

    calls = [{"name": "read", "args": {"path": "/tmp"}, "id": "call_1"}]
    row = serialize_assistant_message("", tool_calls=calls)
    assert row["role"] == "assistant"
    assert row["content"] == ""
    assert len(row["tool_calls"]) == 1
    assert row["tool_calls"][0]["name"] == "read"


def test_serialize_tool_result():
    from context import serialize_tool_result

    row = serialize_tool_result("read", "call_1", '{"status": "success", "data": "contents"}')
    assert row == {
        "role": "tool",
        "content": '{"status": "success", "data": "contents"}',
        "tool_calls": [{"name": "read", "id": "call_1"}],
    }


def test_serialize_tool_result_truncates():
    from context import serialize_tool_result

    long = "y" * 5000
    row = serialize_tool_result("www_ddg", "call_2", long)
    assert len(row["content"]) == 4000
