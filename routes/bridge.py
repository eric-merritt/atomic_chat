"""WebSocket bridge: persistent client agent connections with challenge-response auth."""

import base64
import json
import secrets

from flask import Blueprint
from flask_login import current_user
from flask_sock import Sock

from atomic_client import bridge
from config import SERVER_PRIVATE_KEY, SERVER_PUBLIC_KEY_PEM

bridge_bp = Blueprint("bridge", __name__)
sock = Sock()


@bridge_bp.route("/api/bridge/pubkey", methods=["GET"])
def get_pubkey():
    """Serve the server's RSA public key for client challenge-response auth."""
    return SERVER_PUBLIC_KEY_PEM, 200, {"Content-Type": "text/plain"}


@sock.route("/api/bridge/connect")
def bridge_connect(ws):
    """Persistent WebSocket connection for a client agent bridge.

    Protocol:
      S→C: {"type": "challenge", "nonce": "<hex>"}
      C→S: {"type": "challenge_response", "blob": "<base64 RSA-OAEP encrypted nonce>"}
      S→C: {"type": "authenticated"} | {"type": "auth_failed", "message": "..."}
      S→C: {"type": "tool_call", "call_id": "...", "tool": "...", "args": {...}}
      C→S: {"type": "tool_result", "call_id": "...", "result": {...}}
      C→S: {"type": "ping"}  →  S→C: {"type": "pong"}
    """
    if not current_user.is_authenticated:
        ws.send(json.dumps({"type": "error", "message": "Authentication required"}))
        return

    # ── Challenge-response ────────────────────────────────────────────────────
    nonce = secrets.token_hex(32)
    ws.send(json.dumps({"type": "challenge", "nonce": nonce}))

    try:
        raw = ws.receive(timeout=30)
    except Exception:
        return
    if not raw:
        return

    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        ws.send(json.dumps({"type": "auth_failed", "message": "Invalid JSON"}))
        return

    if msg.get("type") != "challenge_response":
        ws.send(json.dumps({"type": "auth_failed", "message": "Expected challenge_response"}))
        return

    try:
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        blob = base64.b64decode(msg["blob"])
        decrypted = SERVER_PRIVATE_KEY.decrypt(
            blob,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        if decrypted.decode() != nonce:
            raise ValueError("nonce mismatch")
    except Exception as e:
        ws.send(json.dumps({"type": "auth_failed", "message": str(e)}))
        return

    # ── Register and serve ────────────────────────────────────────────────────
    conn = bridge.register(current_user.id, ws)
    ws.send(json.dumps({"type": "authenticated"}))

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if msg.get("type") == "tool_result":
                conn.resolve(msg["call_id"], msg.get("result", {}))
            elif msg.get("type") == "ping":
                ws.send(json.dumps({"type": "pong"}))
    finally:
        bridge.unregister(current_user.id)
