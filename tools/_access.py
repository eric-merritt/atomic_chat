"""Access control for filesystem and bash tools.

Admin + API key → run directly on the server.
Everyone else   → proxy to their connected client agent bridge.
No bridge       → reject with a helpful message.
"""

from tools._output import tool_result


def _current_identity():
    """Resolve (user_id, role) for the calling request.

    Tools run on qwen-agent's pump thread, where copy_current_request_context
    hands out a fresh, blank g — so current_user is None there. The chat route
    stashes fs_user_id/fs_user_role on g for exactly this case; fall back to it
    when current_user is unavailable. Returns (None, None) outside any request.
    """
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            return current_user.id, current_user.role
    except (RuntimeError, AttributeError):
        pass

    try:
        from flask import g
        return getattr(g, "fs_user_id", None), getattr(g, "fs_user_role", None)
    except RuntimeError:
        return None, None


def check_fs_access(tool_name: str, params_str: str):
    """Return None to proceed locally, or a result dict to return immediately."""
    user_id, role = _current_identity()

    if user_id is None:
        return None  # no request context (tests, MCP server) — proceed locally

    if role == "admin":
        return None  # admin always has direct server-side access

    # Proxy to client agent bridge
    from atomic_client import bridge as _bridge
    conn = _bridge.get(user_id)
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
