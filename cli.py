"""CLI entry point for atomic_chat. Run with: uv run python cli.py"""

import json
import os
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

load_dotenv(override=True)

# API host — backend (Flask). In prod both vars point to the same origin.
ATOMIC_HOST = os.environ.get("ATOMIC_HOST", "http://localhost:5000")
# UI host — frontend (Vite dev server proxies /api → Flask). Only differs in local dev.
ATOMIC_UI_HOST = os.environ.get("ATOMIC_UI_HOST", "http://localhost:5173")
CREDS_PATH = Path.home() / ".config" / "atomic_chat" / "credentials.json"

console = Console()


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_creds() -> dict:
    try:
        return json.loads(CREDS_PATH.read_text()) if CREDS_PATH.exists() else {}
    except Exception:
        return {}


def _save_creds(creds: dict):
    CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDS_PATH.write_text(json.dumps(creds, indent=2))


def _make_session(creds: dict) -> requests.Session:
    sess = requests.Session()
    if api_key := os.environ.get("ATOMIC_API_KEY"):
        sess.headers["X-API-Key"] = api_key
    elif session_id := creds.get("session_id"):
        sess.cookies.set("session_id", session_id)
    return sess


def _check_auth(sess: requests.Session) -> bool:
    try:
        return sess.get(f"{ATOMIC_HOST}/api/auth/me", timeout=8).ok
    except Exception:
        return False


# ── Browser auth flow ─────────────────────────────────────────────────────────

def _browser_auth() -> str | None:
    resp = requests.post(f"{ATOMIC_HOST}/api/auth/cli/initiate", timeout=8)
    resp.raise_for_status()
    token = resp.json()["token"]
    url = f"{ATOMIC_UI_HOST}/cli-auth?token={token}"

    console.print(f"\nOpen this URL to authenticate:\n  [link={url}]{url}[/link]\n")
    try:
        subprocess.Popen(["xdg-open", url])
    except Exception:
        pass

    deadline = time.time() + 300
    with Live(Spinner("dots", text="Waiting for browser approval…"), console=console, refresh_per_second=10):
        while time.time() < deadline:
            time.sleep(2)
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
                console.print("[green]✓ Approved![/green]")
                return data["session_id"]
            if status == "denied":
                console.print("[red]✗ Denied.[/red]")
                return None
            if status == "expired":
                console.print("[yellow]Token expired.[/yellow]")
                return None

    console.print("[yellow]Timed out waiting for approval.[/yellow]")
    return None


# ── Auth entry point ──────────────────────────────────────────────────────────

def ensure_auth() -> requests.Session:
    # Fast path: ATOMIC_API_KEY env var
    if api_key := os.environ.get("ATOMIC_API_KEY"):
        sess = requests.Session()
        sess.headers["X-API-Key"] = api_key
        if _check_auth(sess):
            return sess
        console.print("[yellow]ATOMIC_API_KEY is invalid or expired — falling back to browser auth.[/yellow]")

    # Saved session
    creds = _load_creds()
    if creds.get("session_id"):
        sess = _make_session(creds)
        if _check_auth(sess):
            return sess

    # Browser auth flow
    session_id = _browser_auth()
    if not session_id:
        console.print("[red]Authentication failed. Exiting.[/red]")
        raise SystemExit(1)

    _save_creds({"session_id": session_id})
    sess = requests.Session()
    sess.cookies.set("session_id", session_id)
    return sess


# ── Chat streaming ────────────────────────────────────────────────────────────

class _AuthExpired(Exception):
    pass


def _stream_chat(sess: requests.Session, message: str, conversation_id: str | None) -> str | None:
    resp = sess.post(
        f"{ATOMIC_HOST}/api/chat/stream",
        json={"message": message, "conversation_id": conversation_id},
        stream=True,
        timeout=(10, 300),
    )
    if resp.status_code == 401:
        raise _AuthExpired()
    resp.raise_for_status()

    new_conv_id = conversation_id
    console.print("[dim]Agent:[/dim] ", end="")

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "chunk" in ev or "token" in ev:
            print(ev.get("chunk") or ev.get("token", ""), end="", flush=True)
        elif "conversation_id" in ev and ev["conversation_id"]:
            new_conv_id = ev["conversation_id"]
        elif ev.get("type") == "meta" and ev.get("conversation_id"):
            new_conv_id = ev["conversation_id"]
        elif "tool_call" in ev:
            console.print(f"\n  [dim]→ {ev['tool_call'].get('tool')}[/dim]", end="")
        elif "tool_result" in ev:
            console.print(" [dim]✓[/dim]", end="")
        elif "bash_confirm" in ev:
            bc = ev["bash_confirm"]
            console.print(f"\n\n[yellow]Bash requested:[/yellow] [bold]{bc['command']}[/bold]")
            if bc.get("description"):
                console.print(f"  [dim]{bc['description']}[/dim]")
            try:
                approved = input("  Approve? [y/N] ").strip().lower() == "y"
            except (EOFError, KeyboardInterrupt):
                approved = False
            sess.post(
                f"{ATOMIC_HOST}/api/chat/bash_confirm",
                json={"conversation_id": new_conv_id, "approved": approved},
                timeout=8,
            )
        elif "error" in ev:
            console.print(f"\n[red]Error: {ev['error']}[/red]")

    print()
    return new_conv_id


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    sess = ensure_auth()
    conversation_id: str | None = None

    console.print("\n[bold]Atomic Chat CLI[/bold]  [dim]'new' for a new conversation · 'quit' to exit[/dim]\n")
    session = PromptSession()

    with patch_stdout():
        while True:
            try:
                user_input = session.prompt("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "new":
                conversation_id = None
                console.print("  [dim]New conversation started[/dim]\n")
                continue

            try:
                conversation_id = _stream_chat(sess, user_input, conversation_id)
            except _AuthExpired:
                console.print("[yellow]Session expired — re-authenticating…[/yellow]")
                _save_creds({})
                sess = ensure_auth()
                try:
                    conversation_id = _stream_chat(sess, user_input, conversation_id)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]\n")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]\n")


if __name__ == "__main__":
    main()
