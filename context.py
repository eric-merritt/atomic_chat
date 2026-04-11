"""Context pipeline: conversation history loading and serialization.

Converts DB rows to qwen-agent message dicts (role/content/name).
"""

TOOL_RESULT_MAX_CHARS = 4000


def _db_row_to_qwen(row: dict) -> dict:
  """Convert a DB message dict to a qwen-agent message dict.

  qwen-agent format:
  - user: {"role": "user", "content": "..."}
  - assistant: {"role": "assistant", "content": "..."}
  - tool result: {"role": "function", "name": "tool_name", "content": "..."}
  """
  role = row["role"]
  content = row.get("content", "")
  tool_calls = row.get("tool_calls", [])

  if role == "user":
    return {"role": "user", "content": content}

  if role == "assistant":
    return {"role": "assistant", "content": content}

  if role == "tool":
    truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
    tool_name = tool_calls[0]["name"] if tool_calls else "unknown"
  return {"role": "function", "name": tool_name, "content": truncated}

  return {"role": "user", "content": content}


def build_history(db_messages: list[dict]) -> list[dict]:
  """Convert DB message dicts to qwen-agent message dicts."""
  return [_db_row_to_qwen(row) for row in db_messages]


def serialize_user_message(content: str) -> dict:
  """Serialize a user message for DB storage."""
  return {"role": "user", "content": content, "tool_calls": []}


def serialize_assistant_message(content: str, tool_calls: list) -> dict:
  """Serialize an assistant message for DB storage."""
  return {"role": "assistant", "content": content, "tool_calls": tool_calls or []}


def serialize_tool_result(tool_name: str, tool_call_id: str, content: str) -> dict:
  """Serialize a tool result for DB storage."""
  truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
  return {
  "role": "tool",
  "content": truncated,
  "tool_calls": [{"name": tool_name, "id": tool_call_id}],
  }
