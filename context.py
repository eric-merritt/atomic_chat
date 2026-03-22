"""Context pipeline: conversation history loading, replay, and persistence.

Converts between DB rows (dicts with role/content/tool_calls) and
LangChain message types for agent consumption.
"""

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)

TOOL_RESULT_MAX_CHARS = 4000


def _db_row_to_langchain(row: dict):
    """Convert a DB message dict to the corresponding LangChain message.

    Args:
        row: Dict with keys: role, content, tool_calls.

    Returns:
        HumanMessage, AIMessage, or ToolMessage.
    """
    role = row["role"]
    content = row.get("content", "")
    tool_calls = row.get("tool_calls", [])

    if role == "user":
        return HumanMessage(content=content)

    if role == "assistant":
        if tool_calls:
            return AIMessage(content=content, tool_calls=tool_calls)
        return AIMessage(content=content)

    if role == "tool":
        truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
        tool_name = tool_calls[0]["name"] if tool_calls else "unknown"
        tool_call_id = tool_calls[0].get("id", "unknown") if tool_calls else "unknown"
        return ToolMessage(content=truncated, name=tool_name, tool_call_id=tool_call_id)

    # Fallback — treat unknown roles as human messages
    return HumanMessage(content=content)


def build_history(db_messages: list[dict]) -> list:
    """Convert a list of DB message dicts to LangChain messages.

    Args:
        db_messages: List of dicts from ConversationMessage table,
                     ordered by created_at ascending.

    Returns:
        List of LangChain message objects.
    """
    return [_db_row_to_langchain(row) for row in db_messages]


# --- Serialization helpers (LangChain → DB row dicts) ---

def serialize_user_message(content: str) -> dict:
    """Serialize a user message for DB storage."""
    return {"role": "user", "content": content, "tool_calls": []}


def serialize_assistant_message(content: str, tool_calls: list) -> dict:
    """Serialize an assistant message for DB storage."""
    return {"role": "assistant", "content": content, "tool_calls": tool_calls or []}


def serialize_tool_result(tool_name: str, tool_call_id: str, content: str) -> dict:
    """Serialize a tool result for DB storage. Truncates content to 4000 chars."""
    truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
    return {
        "role": "tool",
        "content": truncated,
        "tool_calls": [{"name": tool_name, "id": tool_call_id}],
    }
