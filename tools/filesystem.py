"""Filesystem tools: read, write, and manage files and directories."""

import os
import json
import glob as glob_mod
import shutil
from langchain.tools import tool
from tools._output import tool_result, retry


# ── Read Operations ──────────────────────────────────────────────────────────

@tool
@retry()
def read(path: str, start_line: int = 0, end_line: int = -1) -> str:
    """Read a file and return its contents with line numbers.

    WHEN TO USE: When you need to view the contents of a file.
    WHEN NOT TO USE: When you need file metadata (use info instead).

    Args:
        path: Absolute or relative file path.
        start_line: First line to include (0-indexed). Default: 0 (start of file).
        end_line: Last line to include (exclusive). -1 = read to end.

    Output format:
        {"status": "success", "data": {"path": "...", "content": "...", "lines_returned": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return tool_result(error=f"File not found: {os.path.abspath(path)}")
    except PermissionError:
        return tool_result(error=f"Permission denied: {os.path.abspath(path)}")
    except Exception as e:
        return tool_result(error=str(e))

    end = None if end_line == -1 else end_line
    subset = lines[start_line:end]
    numbered = [f"{i:>6}  {line.rstrip()}" for i, line in enumerate(subset, start=start_line + 1)]
    return tool_result(data={
        "path": os.path.abspath(path),
        "content": "\n".join(numbered),
        "lines_returned": len(numbered),
    })


@tool
@retry()
def info(path: str) -> str:
    """Return metadata about a file: size, modified time, type, line count.

    WHEN TO USE: When you need file metadata without reading its contents.
    WHEN NOT TO USE: When you need the actual file contents (use read instead).

    Args:
        path: Absolute or relative file path.

    Output format:
        {"status": "success", "data": {"path": "...", "exists": true, "size_bytes": N, ...}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return tool_result(error=f"File not found: {os.path.abspath(path)}")
    except Exception as e:
        return tool_result(error=str(e))

    info_dict = {
        "path": os.path.abspath(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
        "is_file": os.path.isfile(path),
        "is_dir": os.path.isdir(path),
    }
    if info_dict["is_file"]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                info_dict["line_count"] = sum(1 for _ in f)
        except Exception:
            info_dict["line_count"] = None
    return tool_result(data=info_dict)


@tool
@retry()
def ls(path: str = ".", recursive: bool = False, pattern: str = "*") -> str:
    """List directory contents, optionally recursive with glob pattern.

    WHEN TO USE: When you need to see what files and directories exist at a path.
    WHEN NOT TO USE: When you need a visual tree structure (use tree instead).

    Args:
        path: Directory to list. Defaults to current directory.
        recursive: If True, walk subdirectories.
        pattern: Glob pattern to filter results (e.g. '*.py').

    Output format:
        {"status": "success", "data": {"path": "...", "count": N, "entries": [...]}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        if recursive:
            entries = sorted(glob_mod.glob(os.path.join(path, "**", pattern), recursive=True))
        else:
            entries = sorted(glob_mod.glob(os.path.join(path, pattern)))
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"path": os.path.abspath(path), "count": len(entries), "entries": entries})


@tool
@retry()
def tree(path: str = ".", max_depth: int = 3, show_hidden: bool = False) -> str:
    """Print the directory tree structure.

    WHEN TO USE: When you need a visual overview of a directory's structure.
    WHEN NOT TO USE: When you need a flat file list (use ls instead).

    Args:
        path: Root directory. Defaults to current directory.
        max_depth: Maximum depth to traverse. Range: 1-10.
        show_hidden: Include dotfiles/dotdirs. Default: False.

    Output format:
        {"status": "success", "data": {"path": "...", "tree": "..."}, "error": ""}
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
    return tool_result(data={"path": os.path.abspath(path), "tree": "\n".join(lines)})


# ── Write Operations ─────────────────────────────────────────────────────────

@tool
@retry()
def write(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    WHEN TO USE: When you need to create a new file or overwrite an existing file entirely.
    WHEN NOT TO USE: When you need to modify part of a file (use replace or insert instead).

    WARNING: This is a DESTRUCTIVE operation. It OVERWRITES the entire file content.
    Any existing content in the file will be permanently lost.

    Args:
        path: Absolute or relative file path.
        content: Full file content to write.

    Output format:
        {"status": "success", "data": {"path": "/abs/path", "bytes_written": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            written = f.write(content)
        return tool_result(data={"path": os.path.abspath(path), "bytes_written": written})
    except PermissionError:
        return tool_result(error=f"Permission denied: {os.path.abspath(path)}")
    except Exception as e:
        return tool_result(error=str(e))


@tool
@retry()
def append(path: str, content: str) -> str:
    """Append content to the end of a file.

    WHEN TO USE: When you need to add content to the end of an existing file.
    WHEN NOT TO USE: When you need to insert content at a specific location (use insert instead).

    Args:
        path: File path to append to.
        content: Content to append.

    Output format:
        {"status": "success", "data": {"path": "/abs/path", "bytes_appended": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            written = f.write(content)
        return tool_result(data={"path": os.path.abspath(path), "bytes_appended": written})
    except Exception as e:
        return tool_result(error=str(e))


@tool
@retry()
def replace(path: str, old: str, new: str, count: int = 1) -> str:
    """Replace exact string occurrences in a file.

    WHEN TO USE: When you need to find and replace specific text in a file.
    WHEN NOT TO USE: When you need to rewrite the entire file (use write instead).

    Args:
        path: File to edit.
        old: Exact string to find. Must exist in the file.
        new: Replacement string.
        count: Max replacements. 0 = replace all occurrences.

    Output format:
        {"status": "success", "data": {"path": "/abs/path", "replacements": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return tool_result(error=str(e))

    if old not in content:
        return tool_result(error=f"String not found in {os.path.abspath(path)}")

    occurrences = content.count(old)
    if count == 0:
        new_content = content.replace(old, new)
        replaced = occurrences
    else:
        new_content = content.replace(old, new, count)
        replaced = min(count, occurrences)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"path": os.path.abspath(path), "replacements": replaced})


@tool
@retry()
def insert_at_line(path: str, line_number: int, content: str) -> str:
    """Insert content at a specific line number (1-indexed).

    WHEN TO USE: When you need to add content at a specific line in a file.
    WHEN NOT TO USE: When you need to add content at the end (use append instead).

    Args:
        path: File to edit.
        line_number: Line number to insert before (1-indexed).
        content: Text to insert.

    Output format:
        {"status": "success", "data": {"path": "/abs/path", "inserted_at_line": N}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return tool_result(error=str(e))

    if not content.endswith("\n"):
        content += "\n"
    lines.insert(line_number - 1, content)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"path": os.path.abspath(path), "inserted_at_line": line_number})


@tool
@retry()
def delete(path: str, start: int = 0, end: int = 0) -> str:
    """Delete a file, empty directory, or a range of lines from a file.

    WARNING: File/directory deletion is IRREVERSIBLE. Deleted files cannot be recovered.
    Line deletion modifies the file in place.

    WHEN TO USE: When you need to delete a file/directory or remove lines from a file.
    WHEN NOT TO USE: When you need to replace content (use replace instead).

    If start and end are both 0, deletes the file/directory.
    Otherwise, deletes lines start-end (1-indexed, inclusive) from the file.

    Args:
        path: Path to delete or file to edit.
        start: First line to delete (1-indexed). 0 = delete the file itself.
        end: Last line to delete (1-indexed, inclusive). 0 = delete the file itself.

    Output format:
        {"status": "success", "data": {"path": "...", "action": "deleted_file"|"deleted_lines", ...}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        if start == 0 and end == 0:
            if os.path.isdir(path):
                os.rmdir(path)
                return tool_result(data={"path": os.path.abspath(path), "action": "deleted_directory"})
            else:
                os.remove(path)
                return tool_result(data={"path": os.path.abspath(path), "action": "deleted_file"})
        else:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            removed_count = len(lines[start - 1:end])
            del lines[start - 1:end]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return tool_result(data={
                "path": os.path.abspath(path),
                "action": "deleted_lines",
                "start": start,
                "end": end,
                "lines_removed": removed_count,
            })
    except Exception as e:
        return tool_result(error=str(e))


# ── File Management ──────────────────────────────────────────────────────────

@tool
@retry()
def copy(src: str, dst: str) -> str:
    """Copy a file or directory.

    WHEN TO USE: When you need to duplicate a file or directory.
    WHEN NOT TO USE: When you need to move/rename (use move instead).

    Args:
        src: Source path.
        dst: Destination path.

    Output format:
        {"status": "success", "data": {"src": "...", "dst": "..."}, "error": ""}
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    try:
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            shutil.copy2(src, dst)
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"src": os.path.abspath(src), "dst": os.path.abspath(dst)})


@tool
@retry()
def move(src: str, dst: str) -> str:
    """Move or rename a file or directory.

    WARNING: If the destination already exists, it will be OVERWRITTEN.

    WHEN TO USE: When you need to move or rename a file or directory.
    WHEN NOT TO USE: When you need to keep the original (use copy instead).

    Args:
        src: Source path.
        dst: Destination path.

    Output format:
        {"status": "success", "data": {"src": "...", "dst": "..."}, "error": ""}
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.move(src, dst)
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"src": os.path.abspath(src), "dst": os.path.abspath(dst)})


@tool
@retry()
def create_directory(path: str) -> str:
    """Create a directory and any missing parents.

    WHEN TO USE: When you need to create a new directory.
    WHEN NOT TO USE: When the directory already exists (this is a no-op with exist_ok=True).

    Args:
        path: Directory path to create.

    Output format:
        {"status": "success", "data": {"path": "/abs/path"}, "error": ""}
    """
    path = os.path.expanduser(path)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        return tool_result(error=str(e))

    return tool_result(data={"path": os.path.abspath(path)})


FILESYSTEM_TOOLS = [
    read,
    info,
    ls,
    tree,
    write,
    append,
    replace,
    insert_at_line,
    delete,
    copy,
    move,
    create_directory,
]
