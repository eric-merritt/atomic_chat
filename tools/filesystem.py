"""Filesystem tools: read, write, and manage files and directories."""

import os
import json
import glob as glob_mod
import shutil
from pathlib import Path

from langchain.tools import tool


# ── Read Operations ──────────────────────────────────────────────────────────

@tool
def read(path: str, start_line: int = 0, end_line: int = -1) -> str:
    """Read a file and return its contents with line numbers.

    Args:
        path: Absolute or relative file path.
        start_line: First line to include (0-indexed).
        end_line: Last line to include (exclusive). -1 = read to end.
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    end = None if end_line == -1 else end_line
    subset = lines[start_line:end]
    numbered = [f"{i:>6}  {line.rstrip()}" for i, line in enumerate(subset, start=start_line + 1)]
    return "\n".join(numbered)


@tool
def info(path: str) -> str:
    """Return metadata about a file: size, modified time, type, line count.

    Args:
        path: Absolute or relative file path.
    """
    path = os.path.expanduser(path)
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


@tool
def ls(path: str = ".", recursive: bool = False, pattern: str = "*") -> str:
    """List directory contents, optionally recursive with glob pattern.

    Args:
        path: Directory to list.
        recursive: If True, walk subdirectories.
        pattern: Glob pattern to filter results (e.g. '*.py').
    """
    path = os.path.expanduser(path)
    if recursive:
        entries = sorted(glob_mod.glob(os.path.join(path, "**", pattern), recursive=True))
    else:
        entries = sorted(glob_mod.glob(os.path.join(path, pattern)))
    return "\n".join(entries)


@tool
def tree(path: str = ".", max_depth: int = 3, show_hidden: bool = False) -> str:
    """Prints the directory tree.

    Args:
        path: Root directory.
        max_depth: Maximum depth to traverse.
        show_hidden: Include dotfiles/dotdirs.
    """
    path = os.path.expanduser(path)
    lines = []

    def _walk(dir_path: str, prefix: str, depth: int):
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


# ── Write Operations ─────────────────────────────────────────────────────────

@tool
def write(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: File path to write.
        content: Full file content.
    """
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        written = f.write(content)
    return f"Wrote {written} bytes to {os.path.abspath(path)}"


@tool
def append(path: str, content: str) -> str:
    """Append content to the end of a file.

    Args:
        path: File path to append to.
        content: Content to append.
    """
    path = os.path.expanduser(path)
    with open(path, "a", encoding="utf-8") as f:
        written = f.write(content)
    return f"Appended {written} bytes to {os.path.abspath(path)}"


@tool
def replace(path: str, old: str, new: str, count: int = 1) -> str:
    """Replace exact string occurrences in a file.

    Args:
        path: File to edit.
        old: Exact string to find.
        new: Replacement string.
        count: Max replacements. 0 = replace all.
    """
    path = os.path.expanduser(path)
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


@tool
def insert(path: str, line_number: int, content: str) -> str:
    """Insert content at a specific line number (1-indexed).

    Args:
        path: File to edit.
        line_number: Line number to insert before (1-indexed).
        content: Text to insert.
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not content.endswith("\n"):
        content += "\n"
    lines.insert(line_number - 1, content)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Inserted at line {line_number} in {os.path.abspath(path)}"


@tool
def delete(path: str, start: int = 0, end: int = 0) -> str:
    """Delete a file, empty directory, or a range of lines from a file.

    If start and end are both 0, deletes the file/directory.
    Otherwise, deletes lines start-end (1-indexed, inclusive) from the file.

    Args:
        path: Path to delete or file to edit.
        start: First line to delete (1-indexed). 0 = delete the file itself.
        end: Last line to delete (1-indexed, inclusive). 0 = delete the file itself.
    """
    path = os.path.expanduser(path)
    if start == 0 and end == 0:
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
        return f"Deleted {os.path.abspath(path)}"
    else:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        removed = lines[start - 1 : end]
        del lines[start - 1 : end]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return f"Deleted lines {start}-{end} ({len(removed)} lines) from {os.path.abspath(path)}"


# ── File Management ──────────────────────────────────────────────────────────

@tool
def copy(src: str, dst: str) -> str:
    """Copy a file or directory.

    Args:
        src: Source path.
        dst: Destination path.
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.copy2(src, dst)
    return f"Copied {src} -> {dst}"


@tool
def move(src: str, dst: str) -> str:
    """Move/rename a file or directory.

    Args:
        src: Source path.
        dst: Destination path.
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.move(src, dst)
    return f"Moved {src} -> {dst}"


@tool
def mkdir(path: str) -> str:
    """Create a directory and any missing parents.

    Args:
        path: Directory path to create.
    """
    path = os.path.expanduser(path)
    os.makedirs(path, exist_ok=True)
    return f"Created directory {os.path.abspath(path)}"


FILESYSTEM_TOOLS = [
    read,
    info,
    ls,
    tree,
    write,
    append,
    replace,
    insert,
    delete,
    copy,
    move,
    mkdir,
]
