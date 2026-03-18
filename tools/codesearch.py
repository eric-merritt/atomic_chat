"""Code search tools: grep, find, definition."""

import os
import re
import glob as glob_mod
import difflib

from langchain.tools import tool


# ── Search Operations ────────────────────────────────────────────────────────

@tool
def grep(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    ignore_case: bool = False,
    context: int = 0,
    max_results: int = 50,
) -> str:
    """Search file contents with regex, returning matches with context.

    Args:
        pattern: Regex pattern to search for.
        path: File or directory to search in.
        file_pattern: Glob to filter which files to search (e.g. '*.py').
        ignore_case: Case-insensitive matching.
        context: Number of lines before/after each match to include.
        max_results: Maximum number of matches to return.
    """
    path = os.path.expanduser(path)
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


@tool
def find(
    path: str = ".",
    name: str = "",
    pattern: str = "",
    extension: str = "",
    contains: str = "",
    max_results: int = 50,
) -> str:
    """Find files by name pattern, extension, or content.

    Args:
        path: Directory to search.
        name: Glob pattern for filename (e.g. 'test_*').
        pattern: Alias for name — glob pattern for filename (e.g. '*.py').
        extension: File extension filter (e.g. '.py').
        contains: Only return files containing this string.
        max_results: Maximum files to return.
    """
    # Allow 'pattern' as an alias for 'name'
    if pattern and not name:
        name = pattern

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

    return "\n".join(matches[:max_results])


@tool
def definition(symbol: str, path: str = ".", file_pattern: str = "*.py") -> str:
    """Find where a function, class, or variable is defined.

    Args:
        symbol: Name of the symbol to find.
        path: Directory to search.
        file_pattern: Glob pattern for files to search.
    """
    patterns = [
        rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        rf"^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*=",
    ]
    combined = "|".join(f"({p})" for p in patterns)
    return grep.invoke({"pattern": combined, "path": path, "file_pattern": file_pattern, "context": 3})


CODESEARCH_TOOLS = [grep, find, definition]
