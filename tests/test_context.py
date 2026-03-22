"""Tests for context pipeline module."""

import json
import pytest


# --- Message replay ---

def test_replay_user_message():
    from context import _db_row_to_langchain
    from langchain_core.messages import HumanMessage

    row = {"role": "user", "content": "hello", "tool_calls": []}
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, HumanMessage)
    assert msg.content == "hello"


def test_replay_assistant_text():
    from context import _db_row_to_langchain
    from langchain_core.messages import AIMessage

    row = {"role": "assistant", "content": "hi there", "tool_calls": []}
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, AIMessage)
    assert msg.content == "hi there"
    assert not msg.tool_calls


def test_replay_assistant_tool_call():
    from context import _db_row_to_langchain
    from langchain_core.messages import AIMessage

    row = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"name": "read", "args": {"path": "/tmp/test"}, "id": "call_1"}],
    }
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, AIMessage)
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0]["name"] == "read"


def test_replay_tool_result():
    from context import _db_row_to_langchain
    from langchain_core.messages import ToolMessage

    row = {
        "role": "tool",
        "content": '{"status": "success", "data": "file contents"}',
        "tool_calls": [{"name": "read", "id": "call_1"}],
    }
    msg = _db_row_to_langchain(row)
    assert isinstance(msg, ToolMessage)
    assert msg.name == "read"
    assert msg.tool_call_id == "call_1"


# --- Truncation ---

def test_tool_result_truncation():
    from context import _db_row_to_langchain

    long_content = "x" * 5000
    row = {"role": "tool", "content": long_content, "tool_calls": [{"name": "web_search", "id": "call_2"}]}
    msg = _db_row_to_langchain(row)
    assert len(msg.content) <= 4000


# --- Build history ---

def test_build_history_ordering():
    from context import build_history
    from langchain_core.messages import HumanMessage, AIMessage

    db_messages = [
        {"role": "user", "content": "first", "tool_calls": []},
        {"role": "assistant", "content": "response1", "tool_calls": []},
        {"role": "user", "content": "second", "tool_calls": []},
    ]
    history = build_history(db_messages)
    assert len(history) == 3
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "first"
    assert isinstance(history[1], AIMessage)
    assert isinstance(history[2], HumanMessage)
    assert history[2].content == "second"


def test_build_history_empty():
    from context import build_history
    assert build_history([]) == []


# --- Serialization for DB ---

def test_serialize_user_message():
    from context import serialize_user_message

    row = serialize_user_message("what is 2+2")
    assert row["role"] == "user"
    assert row["content"] == "what is 2+2"
    assert row["tool_calls"] == []


def test_serialize_assistant_text():
    from context import serialize_assistant_message

    row = serialize_assistant_message("The answer is 4", tool_calls=[])
    assert row["role"] == "assistant"
    assert row["content"] == "The answer is 4"
    assert row["tool_calls"] == []


def test_serialize_assistant_tool_call():
    from context import serialize_assistant_message

    calls = [{"name": "read", "args": {"path": "/tmp"}, "id": "call_1"}]
    row = serialize_assistant_message("", tool_calls=calls)
    assert row["role"] == "assistant"
    assert row["content"] == ""
    assert len(row["tool_calls"]) == 1


def test_serialize_tool_result():
    from context import serialize_tool_result

    row = serialize_tool_result("read", "call_1", '{"status": "success", "data": "contents"}')
    assert row["role"] == "tool"
    assert row["content"] == '{"status": "success", "data": "contents"}'
    assert row["tool_calls"] == [{"name": "read", "id": "call_1"}]


def test_serialize_tool_result_truncates():
    from context import serialize_tool_result

    long = "y" * 5000
    row = serialize_tool_result("web_search", "call_2", long)
    assert len(row["content"]) <= 4000
