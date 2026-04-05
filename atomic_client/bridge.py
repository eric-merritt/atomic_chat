"""Per-user WebSocket connection registry.

When a user's client_agent.py connects, it registers here.
proxy_if_remote() calls conn.call() to forward tool calls over that socket
and block until the result comes back.
"""

import json
import threading
import uuid

# user_id -> _Connection
_registry: dict[str, "_Connection"] = {}
_lock = threading.Lock()


class _Connection:
    def __init__(self, ws, user_id: str):
        self.ws = ws
        self.user_id = user_id
        self._send_lock = threading.Lock()
        self._pending: dict[str, dict] = {}  # call_id -> {"event": Event, "result": None}

    def call(self, tool_name: str, args: dict, timeout: int = 30) -> dict:
        call_id = str(uuid.uuid4())
        event = threading.Event()
        self._pending[call_id] = {"event": event, "result": None}

        try:
            with self._send_lock:
                self.ws.send(json.dumps({
                    "type": "tool_call",
                    "call_id": call_id,
                    "tool": tool_name,
                    "args": args,
                }))
        except Exception as e:
            self._pending.pop(call_id, None)
            return {"status": "error", "data": None, "error": f"Send to client agent failed: {e}"}

        if not event.wait(timeout=timeout):
            self._pending.pop(call_id, None)
            return {"status": "error", "data": None, "error": "Client agent timed out"}

        return self._pending.pop(call_id)["result"]

    def resolve(self, call_id: str, result: dict):
        entry = self._pending.get(call_id)
        if entry:
            entry["result"] = result
            entry["event"].set()


def register(user_id: str, ws) -> "_Connection":
    conn = _Connection(ws, user_id)
    with _lock:
        _registry[user_id] = conn
    return conn


def unregister(user_id: str):
    with _lock:
        _registry.pop(user_id, None)


def get(user_id: str) -> "_Connection | None":
    return _registry.get(user_id)
