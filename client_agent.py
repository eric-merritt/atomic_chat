#!/usr/bin/env python3
"""
Client agent for agent.eric-merritt.com

Connects to the server via WebSocket. The server runs the LLM; when it
needs to call a tool (read_file, grep, etc.) the call is sent here for
local execution on YOUR machine, and the result is returned to the server
so the LLM can continue reasoning.

Usage:
    python client_agent.py                          # interactive chat
    python client_agent.py --message "read my code" # one-shot
    python client_agent.py --server ws://localhost:5000/api/chat/ws

Environment:
    AGENT_API_KEY   — your external API key (or pass --key)
    AGENT_SERVER    — WebSocket URL (default: wss://agent.eric-merritt.com/api/chat/ws)
"""

import argparse
import json
import os
import sys

from websockets.sync.client import connect as ws_connect


# ── Local tool implementations ────────────────────────────────────────────────
# Only safe, read-heavy tools are executed client-side.  Write tools require
# explicit --allow-writes flag.

def _tool_read_file(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    start = params.get("start_line", 0)
    end = params.get("end_line", -1)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    subset = lines[start:None if end == -1 else end]
    numbered = [f"{i:>6}  {line.rstrip()}" for i, line in enumerate(subset, start=start + 1)]
    return "\n".join(numbered)


def _tool_file_info(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    stat = os.stat(path)
    info = {
        "path": os.path.abspath(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
        "is_file": os.path.isfile(path),
        "is_dir": os.path.isdir(path),
    }
    if info["is_file"]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                info["line_count"] = sum(1 for _ in f)
        except Exception:
            info["line_count"] = None
    return json.dumps(info, indent=2)


def _tool_list_dir(params: dict) -> str:
    import glob as glob_mod
    path = os.path.expanduser(params.get("path", "."))
    recursive = params.get("recursive", False)
    pattern = params.get("pattern", "*")
    if recursive:
        entries = sorted(glob_mod.glob(os.path.join(path, "**", pattern), recursive=True))
    else:
        entries = sorted(glob_mod.glob(os.path.join(path, pattern)))
    return "\n".join(entries)


def _tool_tree(params: dict) -> str:
    path = os.path.expanduser(params.get("path", "."))
    max_depth = params.get("max_depth", 3)
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
        dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e))]
        for f in files:
            lines.append(f"{prefix}{f}")
        for d in dirs:
            lines.append(f"{prefix}{d}/")
            _walk(os.path.join(dir_path, d), prefix + "  ", depth + 1)

    lines.append(f"{os.path.basename(os.path.abspath(path))}/")
    _walk(path, "  ", 1)
    return "\n".join(lines)


def _tool_grep(params: dict) -> str:
    import re
    import glob as glob_mod
    pattern = params.get("pattern", "")
    path = os.path.expanduser(params.get("path", "."))
    file_pattern = params.get("file_pattern", "*")
    ignore_case = params.get("ignore_case", False)
    context = params.get("context", 0)
    max_results = params.get("max_results", 50)

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    results = []

    if os.path.isfile(path):
        files = [path]
    else:
        files = sorted(glob_mod.glob(os.path.join(path, "**", file_pattern), recursive=True))

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
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                snippet = []
                for j in range(start, end):
                    marker = ">" if j == i else " "
                    snippet.append(f"  {marker} {j + 1:>5}  {lines[j].rstrip()}")
                results.append(f"{filepath}:{i + 1}\n" + "\n".join(snippet))
                if len(results) >= max_results:
                    return "\n\n".join(results) + f"\n... (truncated at {max_results} results)"

    if not results:
        return f"No matches for /{pattern}/ in {path}"
    return "\n\n".join(results)


def _tool_find_files(params: dict) -> str:
    import glob as glob_mod
    path = os.path.expanduser(params.get("path", "."))
    name = params.get("name", "") or params.get("pattern", "")
    extension = params.get("extension", "")
    contains = params.get("contains", "")
    max_results = params.get("max_results", 50)

    pat = name if name else "*"
    if extension:
        if not extension.startswith("."):
            extension = "." + extension
        pat = f"*{extension}" if not name else pat

    matches = sorted(glob_mod.glob(os.path.join(path, "**", pat), recursive=True))
    matches = [m for m in matches if os.path.isfile(m)]

    if extension and name:
        matches = [m for m in matches if m.endswith(extension)]

    if contains:
        filtered = []
        for m in matches:
            try:
                with open(m, "r", encoding="utf-8", errors="replace") as f:
                    if contains in f.read():
                        filtered.append(m)
            except (PermissionError, OSError):
                continue
        matches = filtered

    return "\n".join(matches[:max_results])


def _tool_find_definition(params: dict) -> str:
    import re
    symbol = params.get("symbol", "")
    path = params.get("path", ".")
    file_pattern = params.get("file_pattern", "*.py")
    patterns = [
        rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        rf"^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*=",
    ]
    combined = "|".join(f"({p})" for p in patterns)
    return _tool_grep({
        "pattern": combined,
        "path": path,
        "file_pattern": file_pattern,
        "context": 3,
    })


# ── Write tools (gated behind --allow-writes) ────────────────────────────────

def _tool_write_file(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    content = params.get("content", "")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        written = f.write(content)
    return f"Wrote {written} bytes to {os.path.abspath(path)}"


def _tool_append_file(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    content = params.get("content", "")
    with open(path, "a", encoding="utf-8") as f:
        written = f.write(content)
    return f"Appended {written} bytes to {os.path.abspath(path)}"


def _tool_replace_in_file(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    old = params.get("old", "")
    new = params.get("new", "")
    count = params.get("count", 1)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        return f"ERROR: String not found in {path}"
    occurrences = content.count(old)
    if count == 0:
        new_content = content.replace(old, new)
        replaced = occurrences
    else:
        new_content = content.replace(old, new, count)
        replaced = min(count, occurrences)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"Replaced {replaced} occurrence(s) in {os.path.abspath(path)}"


def _tool_insert_at_line(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    line_number = params.get("line_number", 1)
    content = params.get("content", "")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not content.endswith("\n"):
        content += "\n"
    lines.insert(line_number - 1, content)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Inserted at line {line_number} in {os.path.abspath(path)}"


def _tool_delete_lines(params: dict) -> str:
    path = os.path.expanduser(params.get("path", ""))
    start = params.get("start", 1)
    end = params.get("end", 1)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    removed = lines[start - 1:end]
    del lines[start - 1:end]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Deleted lines {start}-{end} ({len(removed)} lines) from {os.path.abspath(path)}"


# ── Tool registry ────────────────────────────────────────────────────────────

READ_TOOLS = {
    "read": _tool_read_file,
    "info": _tool_file_info,
    "ls": _tool_list_dir,
    "tree": _tool_tree,
    "grep": _tool_grep,
    "find": _tool_find_files,
    "definition": _tool_find_definition,
}

WRITE_TOOLS = {
    "write": _tool_write_file,
    "append": _tool_append_file,
    "replace": _tool_replace_in_file,
    "insert": _tool_insert_at_line,
    "delete": _tool_delete_lines,
}


def execute_tool(name: str, params: dict, allow_writes: bool) -> str:
    """Execute a tool by name, returning the result string."""
    if name in READ_TOOLS:
        return READ_TOOLS[name](params)

    if name in WRITE_TOOLS:
        if not allow_writes:
            return f"REFUSED: write tool '{name}' blocked (run with --allow-writes to enable)"
        return WRITE_TOOLS[name](params)

    return f"UNSUPPORTED: tool '{name}' is not available on this client"


# ── WebSocket client loop ────────────────────────────────────────────────────

def chat_session(server_url: str, api_key: str, message: str, allow_writes: bool):
    """Connect to the server, send a message, handle tool calls, print response."""
    print(f"\033[90mConnecting to {server_url}...\033[0m")

    with ws_connect(server_url) as ws:
        # Send auth + message
        ws.send(json.dumps({"api_key": api_key, "message": message}))

        while True:
            try:
                raw = ws.recv()
            except Exception:
                break

            if raw is None:
                break

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                print(f"\033[31m[bad frame] {raw[:200]}\033[0m")
                continue

            if "token" in event:
                print(event["token"], end="", flush=True)

            elif "tool_call" in event:
                tc = event["tool_call"]
                tool_name = tc["tool"]
                tool_params = tc.get("params", {})
                tool_id = tc.get("id", "")

                print(f"\n\033[33m[tool] {tool_name}({json.dumps(tool_params, indent=None)})\033[0m")

                try:
                    result = execute_tool(tool_name, tool_params, allow_writes)
                except Exception as e:
                    result = f"ERROR: {e}"

                # Show truncated result
                preview = result[:200] + "..." if len(result) > 200 else result
                print(f"\033[90m[result] {preview}\033[0m")

                ws.send(json.dumps({
                    "tool_result": {"id": tool_id, "output": result}
                }))

            elif "error" in event:
                print(f"\n\033[31m[error] {event['error']}\033[0m")

            elif event.get("done"):
                break

    print()  # final newline


def interactive_loop(server_url: str, api_key: str, allow_writes: bool):
    """REPL — enter messages, get responses with local tool execution."""
    print("Agent client ready. Type 'quit' to exit.\n")
    while True:
        try:
            msg = input("\033[1mYou:\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg.lower() in ("quit", "exit"):
            break

        print("\033[1mAgent:\033[0m ", end="")
        try:
            chat_session(server_url, api_key, msg, allow_writes)
        except Exception as e:
            print(f"\n\033[31mConnection error: {e}\033[0m")


def main():
    parser = argparse.ArgumentParser(
        description="Client agent for agent.eric-merritt.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python client_agent.py
  python client_agent.py --message "list files in ~/projects"
  python client_agent.py --allow-writes --message "fix the typo in main.py"
  AGENT_API_KEY=mykey python client_agent.py
""",
    )
    parser.add_argument("--server", default=os.environ.get("AGENT_SERVER", "wss://agent.eric-merritt.com/api/chat/ws"),
                        help="WebSocket URL (default: wss://agent.eric-merritt.com/api/chat/ws)")
    parser.add_argument("--key", default=os.environ.get("AGENT_API_KEY", ""),
                        help="API key (or set AGENT_API_KEY env var)")
    parser.add_argument("--message", "-m", default="", help="One-shot message (skip interactive mode)")
    parser.add_argument("--allow-writes", action="store_true",
                        help="Allow the agent to write/modify files on your machine")
    args = parser.parse_args()

    if not args.key:
        print("Error: API key required. Set AGENT_API_KEY or pass --key", file=sys.stderr)
        sys.exit(1)

    if args.message:
        print("\033[1mAgent:\033[0m ", end="")
        chat_session(args.server, args.key, args.message, args.allow_writes)
    else:
        interactive_loop(args.server, args.key, args.allow_writes)


if __name__ == "__main__":
    main()
