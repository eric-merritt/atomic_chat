#!/usr/bin/env python3
"""
Atomic Chat — client agent bridge

Connects to the server, authenticates, then serves filesystem and bash
tool calls on behalf of the logged-in user.

Environment (loaded from .env.client):
    AGENT_SERVER   — WebSocket URL for the bridge endpoint
    ATOMIC_HOST    — Base HTTP URL for the server (pubkey, auth)
    AGENT_API_KEY  — Optional; session auth is used if absent
"""

import argparse
import base64
import json
import os
import shutil
import stat as stat_mod
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import requests
from websockets.sync.client import connect as ws_connect
from dotenv import load_dotenv

_IS_FROZEN = getattr(sys, "frozen", False)


def _find_env_file() -> Path | None:
    home_cfg = Path.home() / ".atomic_chat" / ".env.client"
    if _IS_FROZEN:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "AtomicChat" / ".env.client",
            home_cfg,
            Path(sys.executable).parent / ".env.client",
        ]
    else:
        candidates = [Path(__file__).parent / ".env.client", home_cfg]
    return next((p for p in candidates if p.exists()), None)


_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file, override=True)

# ── Config ────────────────────────────────────────────────────────────────────
ATOMIC_HOST  = os.environ.get("ATOMIC_HOST",  "https://agent.eric-merritt.com")
AGENT_SERVER = os.environ.get("AGENT_SERVER", "wss://agent.eric-merritt.com/api/bridge/connect")
ALLOWED_PATHS = [
    Path(p.strip()).expanduser().resolve()
    for p in os.environ.get("ALLOWED_PATHS", str(Path.home())).split(",")
    if p.strip()
]


def _config_dir() -> Path:
    if _IS_FROZEN and sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "AtomicChat"
    return Path.home() / ".config" / "atomic_chat"


_CONFIG_DIR     = _config_dir()
CREDS_PATH      = _CONFIG_DIR / "credentials.json"
DISCLAIMER_PATH = _CONFIG_DIR / "bash_disclaimer_accepted"


# ── Credentials / session auth ────────────────────────────────────────────────

def _load_creds() -> dict:
    try:
        return json.loads(CREDS_PATH.read_text()) if CREDS_PATH.exists() else {}
    except Exception:
        return {}


def _save_creds(creds: dict):
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 0o600: credentials must not be world-readable
    fd = os.open(CREDS_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(creds, indent=2))


def _check_session(session_id: str) -> bool:
    try:
        r = requests.get(
            f"{ATOMIC_HOST}/api/auth/me",
            cookies={"session_id": session_id},
            timeout=8,
        )
        return r.ok
    except Exception:
        return False


def _browser_auth() -> str | None:
    """Open browser approval flow, return session_id or None."""
    try:
        resp = requests.post(f"{ATOMIC_HOST}/api/auth/cli/initiate", timeout=8)
        resp.raise_for_status()
    except Exception as e:
        print(f"[error] Could not reach server: {e}", file=sys.stderr)
        return None

    token = resp.json()["token"]
    url   = f"{ATOMIC_HOST}/cli-auth?token={token}"
    print(f"\nOpen this URL to authenticate:\n  {url}\n")
    try:
        if sys.platform == "win32":
            os.startfile(url)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception:
        pass

    deadline = time.time() + 300
    print("Waiting for browser approval", end="", flush=True)
    while time.time() < deadline:
        time.sleep(3)
        print(".", end="", flush=True)
        try:
            data = requests.get(
                f"{ATOMIC_HOST}/api/auth/cli/poll",
                params={"token": token},
                timeout=8,
            ).json()
        except Exception:
            continue
        status = data.get("status")
        if status == "approved":
            print(" approved!")
            return data["session_id"]
        if status in ("denied", "expired"):
            print(f" {status}.")
            return None
    print(" timed out.")
    return None


def ensure_session() -> str:
    """Return a valid session_id, triggering browser auth if needed."""
    creds = _load_creds()
    if sid := creds.get("session_id"):
        if _check_session(sid):
            return sid

    sid = _browser_auth()
    if not sid:
        print("[error] Authentication failed.", file=sys.stderr)
        sys.exit(1)

    _save_creds({"session_id": sid})
    return sid


# ── Challenge-response ────────────────────────────────────────────────────────

def do_challenge_response(ws) -> bool:
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        pubkey_pem = requests.get(f"{ATOMIC_HOST}/api/bridge/pubkey", timeout=8).text
        public_key = serialization.load_pem_public_key(pubkey_pem.encode())
    except Exception as e:
        print(f"[error] Could not fetch server public key: {e}", file=sys.stderr)
        return False

    raw = ws.recv()
    msg = json.loads(raw)
    if msg.get("type") != "challenge":
        print(f"[error] Expected challenge, got: {msg.get('type')}", file=sys.stderr)
        return False

    encrypted = public_key.encrypt(
        msg["nonce"].encode(),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    ws.send(json.dumps({
        "type": "challenge_response",
        "blob": base64.b64encode(encrypted).decode(),
    }))

    raw = ws.recv()
    msg = json.loads(raw)
    if msg.get("type") == "authenticated":
        return True
    print(f"[error] Auth failed: {msg.get('message', msg)}", file=sys.stderr)
    return False


# ── Bash disclaimer ───────────────────────────────────────────────────────────

def _ensure_bash_disclaimer():
    if DISCLAIMER_PATH.exists():
        return
    print("\n" + "=" * 60)
    print("  NOTICE — Bash Tool")
    print("=" * 60)
    print(
        "\nThe agent can generate and execute shell commands on YOUR machine.\n"
        "\n  • Commands run as YOUR user account\n"
        "  • Back up important files before proceeding\n"
        "  • Review each command before approving it\n"
        "  • Anthropic/Eric are not responsible for agent-generated commands\n"
    )
    try:
        answer = input("I understand and accept [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer != "y":
        print("Bash tool disabled. Re-run the agent to reconsider.")
        sys.exit(0)
    DISCLAIMER_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISCLAIMER_PATH.touch()
    print("Bash tool enabled.\n")


# ── Path guard ────────────────────────────────────────────────────────────────

def _get_path(params: dict, default: str = "") -> str:
    """Expand and validate a path param against ALLOWED_PATHS."""
    path = os.path.expanduser(params.get("path", default))
    try:
        target = Path(path).resolve()
    except Exception:
        raise PermissionError(f"Invalid path: {path!r}")
    if not any(target == ap or target.is_relative_to(ap) for ap in ALLOWED_PATHS):
        allowed = ", ".join(str(p) for p in ALLOWED_PATHS)
        raise PermissionError(
            f"Path {str(target)!r} is outside ALLOWED_PATHS ({allowed}). "
            "Edit ALLOWED_PATHS in .env.client to grant access."
        )
    return path


# ── Local tool implementations ────────────────────────────────────────────────

def _tool_fs_read(params: dict) -> str:
    path  = _get_path(params)
    start = params.get("start_line", 0)
    end   = params.get("end_line", -1)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    subset   = lines[start:None if end == -1 else end]
    numbered = [f"{i:>6}  {line.rstrip()}" for i, line in enumerate(subset, start=start + 1)]
    return "\n".join(numbered)


def _tool_fs_info(params: dict) -> str:
    path = _get_path(params)
    st   = os.stat(path)
    info = {
        "path":       os.path.abspath(path),
        "size_bytes": st.st_size,
        "modified":   st.st_mtime,
        "is_file":    stat_mod.S_ISREG(st.st_mode),
        "is_dir":     stat_mod.S_ISDIR(st.st_mode),
    }
    if info["is_file"]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                info["line_count"] = sum(1 for _ in f)
        except Exception:
            info["line_count"] = None
    return json.dumps(info, indent=2)


def _tool_fs_tree(params: dict) -> str:
    path        = _get_path(params, ".")
    max_depth   = params.get("max_depth", 3)
    show_hidden = params.get("show_hidden", False)
    lines = []

    def _walk(dir_path, prefix, depth):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        for e in entries:
            full = os.path.join(dir_path, e)
            if os.path.isdir(full):
                lines.append(f"{prefix}{e}/")
                _walk(full, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{e}")

    lines.append(f"{os.path.basename(os.path.abspath(path))}/")
    _walk(path, "  ", 1)
    return "\n".join(lines)


def _tool_fs_grep(params: dict) -> str:
    import re, glob as glob_mod
    pattern     = params.get("pattern", "")
    path        = _get_path(params, ".")
    ignore_case = params.get("case_sensitive", False) is False
    context     = params.get("context", 0)
    max_results = params.get("max_results", 50)

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    results = []

    files = [path] if os.path.isfile(path) else \
            sorted(glob_mod.glob(os.path.join(path, "**", "*"), recursive=True))

    for filepath in files:
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (PermissionError, OSError):
            continue
        for i, line in enumerate(lines):
            if regex.search(line):
                s = max(0, i - context)
                e = min(len(lines), i + context + 1)
                snippet = [f"  {'>' if j == i else ' '} {j+1:>5}  {lines[j].rstrip()}" for j in range(s, e)]
                results.append(f"{filepath}:{i+1}\n" + "\n".join(snippet))
                if len(results) >= max_results:
                    return "\n\n".join(results) + f"\n... (truncated at {max_results})"
    return "\n\n".join(results) if results else f"No matches for /{pattern}/ in {path}"


def _tool_fs_find_def(params: dict) -> str:
    import re
    symbol = params.get("symbol", "") or params.get("name", "")
    patterns = [
        rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        rf"^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*=",
    ]
    return _tool_fs_grep({"pattern": "|".join(f"({p})" for p in patterns),
                          "path": params.get("path", "."), "context": 3})


def _tool_fs_write(params: dict) -> str:
    path    = _get_path(params)
    content = params.get("content", "")
    mode    = params.get("mode", "append")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w" if mode == "overwrite" else "a", encoding="utf-8") as f:
        written = f.write(content)
    return f"{'Wrote' if mode == 'overwrite' else 'Appended'} {written} bytes to {os.path.abspath(path)}"


def _tool_fs_replace(params: dict) -> str:
    path        = _get_path(params)
    start_line  = params.get("start_line", 1)
    end_line    = params.get("end_line", 1)
    replacement = params.get("replacement", "")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    s = start_line - 1
    e = len(lines) if end_line == -1 else end_line
    new_line = replacement if replacement.endswith("\n") else replacement + "\n"
    lines = lines[:s] + [new_line] + lines[e:]
    # write to temp then rename so a mid-write crash doesn't truncate the original
    with tempfile.NamedTemporaryFile("w", dir=Path(path).parent, delete=False, encoding="utf-8") as tmp:
        tmp.writelines(lines)
        tmp_path = tmp.name
    shutil.move(tmp_path, path)
    return f"Replaced lines {start_line}-{end_line} in {os.path.abspath(path)}"


def _tool_bash(params: dict) -> str:
    _ensure_bash_disclaimer()
    command     = (params.get("command") or "").strip()
    description = (params.get("description") or "").strip()
    if not command:
        return "ERROR: command is required"

    print(f"\n[bash] {description}")
    print(f"  $ {command}")
    try:
        answer = input("Run? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer != "y":
        return "User declined."

    try:
        result = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return json.dumps({"stdout": None, "stderr": "Command timed out after 120s", "returncode": -1})
    return json.dumps({
        "stdout": (result.stdout or "")[:1_000_000] or None,
        "stderr": (result.stderr or "")[:100_000] or None,
        "returncode": result.returncode,
    })


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS: dict[str, callable] = {
    "fs_read":     _tool_fs_read,
    "fs_info":     _tool_fs_info,
    "fs_tree":     _tool_fs_tree,
    "fs_grep":     _tool_fs_grep,
    "fs_find_def": _tool_fs_find_def,
    "fs_write":    _tool_fs_write,
    "fs_replace":  _tool_fs_replace,
    "bash":        _tool_bash,
}


def execute_tool(name: str, params: dict) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"status": "error", "data": None, "error": f"Tool '{name}' not available on this client"}
    try:
        output = fn(params)
        return {"status": "success", "data": output, "error": None}
    except Exception as e:
        return {"status": "error", "data": None, "error": str(e)}


# ── Bridge daemon ─────────────────────────────────────────────────────────────

def run_bridge(session_id: str, server_url: str, reconnect: bool = True):
    headers = {"Cookie": f"session_id={session_id}"}

    while True:
        print(f"[bridge] Connecting to {server_url}...")
        try:
            with ws_connect(server_url, additional_headers=headers) as ws:
                if not do_challenge_response(ws):
                    print("[bridge] Authentication failed — re-authenticating...")
                    _save_creds({})
                    return

                print("[bridge] Connected and authenticated. Ready.")

                while True:
                    try:
                        raw = ws.recv()
                    except Exception:
                        break
                    if raw is None:
                        break

                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    msg_type = msg.get("type")

                    if msg_type == "tool_call":
                        call_id   = msg["call_id"]
                        tool_name = msg["tool"]
                        args      = msg.get("args", {})
                        print(f"[tool] {tool_name}({json.dumps(args, separators=(',', ':'))[:80]})")
                        result = execute_tool(tool_name, args)
                        ws.send(json.dumps({
                            "type": "tool_result",
                            "call_id": call_id,
                            "result": result,
                        }))
                    elif msg_type == "error":
                        print(f"[bridge] Server error: {msg.get('message')}")
                    # pong: health-check reply, no action needed

        except KeyboardInterrupt:
            print("\n[bridge] Stopped.")
            return
        except Exception as e:
            print(f"[bridge] Disconnected: {e}")

        if not reconnect:
            return

        print("[bridge] Reconnecting in 5s...")
        time.sleep(5)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Atomic Chat — client agent bridge")
    parser.add_argument("--server", default=AGENT_SERVER, help="Bridge WebSocket URL")
    parser.add_argument("--no-reconnect", action="store_true", help="Exit instead of reconnecting on disconnect")
    args = parser.parse_args()

    session_id = ensure_session()
    run_bridge(session_id, server_url=args.server, reconnect=not args.no_reconnect)


if __name__ == "__main__":
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _log_path = _CONFIG_DIR / "atomic-chat-agent.log"

    class _Tee:
        def __init__(self, a, b): self._a, self._b = a, b
        def write(self, s): self._a.write(s); self._b.write(s)
        def flush(self): self._a.flush(); self._b.flush()
        def isatty(self): return False

    _log_fh = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)

    print(f"[agent] Log: {_log_path}")

    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nFatal error — press Enter to exit...")
        sys.exit(1)
