"""Standardized tool output format."""

import json


def tool_result(data=None, error: str = "") -> str:
    """Return a standardized JSON response string.

    All tools MUST return the output of this function.

    Args:
        data: The tool's result payload. Any JSON-serializable value.
        error: Error message. If non-empty, status is "error".

    Returns:
        JSON string: {"status": "success"|"error", "data": ..., "error": ""}
    """
    if error:
        return json.dumps({"status": "error", "data": None, "error": error})
    return json.dumps({"status": "success", "data": data, "error": ""})
