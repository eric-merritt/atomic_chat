"""Access control for filesystem and bash tools.

Admin + API key → run directly on the server.
Everyone else   → proxy to their connected client agent bridge.
No bridge       → reject with a helpful message.
"""

from tools._output import tool_result


def check_fs_access(tool_name: str, params_str: str):
    """Return None to proceed locally, or a result dict to return immediately."""
    try:
        from flask import g
        from flask_login import current_user
        authenticated = current_user.is_authenticated
    except RuntimeError:
        return None  # outside Flask request context (tests, MCP server, etc.)

    if not authenticated:
        return None  # auth_guard already blocks unauthenticated requests

    if current_user.role == "admin" and getattr(g, "auth_via_api_key", False):
        return None  # full server access

    # Proxy to client agent bridge
    from atomic_client import bridge as _bridge
    conn = _bridge.get(current_user.id)
    if conn is None:
        return tool_result(error=(
            "Filesystem and bash tools run on your local machine. "
            "Download and run the client agent to connect: "
            "https://agent.eric-merritt.com"
        ))

    import json5
    try:
        params = json5.loads(params_str)
    except Exception:
        params = {}

    return conn.call(tool_name, params)
