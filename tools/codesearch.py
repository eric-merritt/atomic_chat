"""Code search tools: grep, find, definition."""

import os
import re
import glob as glob_mod

from langchain.tools import tool
from tools._output import tool_result, retry


# ── Search Operations ────────────────────────────────────────────────────────

@tool
@retry()
def grep(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    ignore_case: bool = False,
    context: int = 0,
    max_results: int = 50,
) -> str:
    """Search file contents with regex, returning matches with context.

    WHEN TO USE: When you need to search file contents for a pattern or string.
    WHEN NOT TO USE: When you need to find files by name (use find instead).

    Args:
        pattern: Regex pattern to search for. Must be non-empty.
        path: File or directory to search in. Defaults to current directory.
        file_pattern: Glob to filter which files to search (e.g. '*.py').
        ignore_case: Case-insensitive matching.
        context: Number of lines before/after each match to include.
        max_results: Maximum number of matches to return. Range: 1-500.

    Output format:
        {"status": "success", "data": {"pattern": "...", "count": N, "matches": [{"file": "...", "line": N, "snippet": "..."}]}, "error": ""}
    """
    if not pattern or not pattern.strip():
        return tool_result(error="pattern must be a non-empty string")

    path = os.path.expanduser(path)
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return tool_result(error=f"Invalid regex pattern: {e}")

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
                results.append({
                    "file": filepath,
                    "line": i + 1,
                    "snippet": "\n".join(snippet),
                })
                if len(results) >= max_results:
                    return tool_result(data={
                        "pattern": pattern,
                        "count": len(results),
                        "truncated": True,
                        "matches": results,
                    })

    if not results:
        return tool_result(data={"pattern": pattern, "count": 0, "matches": []})

    return tool_result(data={
        "pattern": pattern,
        "count": len(results),
        "truncated": False,
        "matches": results,
    })


@tool
@retry()
def find(
    path: str = ".",
    name: str = "",
    extension: str = "",
    contains: str = "",
    max_results: int = 50,
) -> str:
    """Find files by name pattern, extension, or content.

    WHEN TO USE: When you need to locate files by name, extension, or content.
    WHEN NOT TO USE: When you need to search file CONTENTS with regex (use grep instead).

    Args:
        path: Directory to search. Defaults to current directory.
        name: Glob pattern for filename (e.g. "test_*", "*.py"). If empty, matches all files.
        extension: File extension filter (e.g. ".py", "py"). Do not combine with name.
        contains: Only return files containing this exact string.
        max_results: Maximum files to return. Range: 1-500.

    Output format:
        {"status": "success", "data": {"path": "...", "count": N, "files": [...]}, "error": ""}
    """
    path = os.path.expanduser(path)
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

    files = matches[:max_results]
    return tool_result(data={
        "path": path,
        "count": len(files),
        "files": files,
    })


@tool
@retry()
def definition(symbol: str, path: str = ".", file_pattern: str = "*.py") -> str:
    """Find where a function, class, or variable is defined.

    WHEN TO USE: When you need to find the source definition of a specific symbol.
    WHEN NOT TO USE: When you need to find all usages of a symbol (use grep instead).

    Args:
        symbol: Name of the symbol to find. Must be non-empty.
        path: Directory to search. Defaults to current directory.
        file_pattern: Glob pattern for files to search (e.g. "*.py", "*.js").

    Output format:
        {"status": "success", "data": {"symbol": "...", "pattern": "...", "count": N, "matches": [...]}, "error": ""}
    """
    if not symbol or not symbol.strip():
        return tool_result(error="symbol must be a non-empty string")

    patterns = [
        rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        rf"^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*=",
    ]
    combined = "|".join(f"({p})" for p in patterns)
    return grep.invoke({"pattern": combined, "path": path, "file_pattern": file_pattern, "context": 3})


CODESEARCH_TOOLS = [grep, find, definition]
