# Subagent Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the monolithic 27-tool agent into 5 specialized MCP HTTP subagents (filesystem, codesearch, web, marketplace, dispatcher) with strict prompt discipline, rate limiting, and quality control.

**Architecture:** Each subagent is a FastMCP server running on its own port with `streamable-http` transport. Subagents are dumb tool executors returning structured JSON. The dispatcher orchestrates them, evaluates result quality via LLM self-eval, and retries on bad data. All agents sit behind nginx reverse proxy.

**Tech Stack:** Python 3.12, FastMCP (`mcp[cli]`), Starlette/Uvicorn (via FastMCP), LangChain + ChatOllama (for dispatcher LLM calls), httpx (async HTTP client for dispatcher→subagent calls), existing Flask chat UI updated to call agents via HTTP.

**Spec:** `docs/superpowers/specs/2026-03-10-subagent-architecture-design.md`

---

## File Structure

```
agentic_w_langchain_ollama/
├── config.py                 # Central config: ports, models, rate limits
├── tools/
│   ├── __init__.py           # Re-exports grouped tool lists
│   ├── filesystem.py         # read_file, file_info, list_dir, tree, write_file,
│   │                         # append_file, replace_in_file, insert_at_line,
│   │                         # delete_lines, copy_file, move_file, delete_file, make_dir
│   ├── codesearch.py         # grep, find_files, find_definition
│   ├── web.py                # web_search, fetch_url
│   └── marketplace.py        # ebay_search, ebay_sold_search, ebay_deep_scan,
│                             # amazon_search, craigslist_search, craigslist_multi_search
│                             # (includes helper functions: _parse_ebay_listings,
│                             #  _extract_gpu_model, _parse_shipping_cost,
│                             #  _parse_amazon_listings, _parse_craigslist_listings,
│                             #  _craigslist_search_city, EBAY_SORT_OPTIONS,
│                             #  CRAIGSLIST_DENVER_AREA, CRAIGSLIST_SHIPPING_CITIES)
├── agents/
│   ├── base.py               # create_mcp_agent() factory: FastMCP server setup,
│   │                         # tool registration, health endpoint, prompt discipline
│   ├── filesystem.py         # Port 8101 — filesystem agent
│   ├── codesearch.py         # Port 8102 — code search agent
│   ├── web.py                # Port 8103 — web agent
│   ├── marketplace.py        # Port 8104 — marketplace agent
│   └── dispatcher.py         # Port 8105 — dispatcher/analyst agent
├── nginx/
│   └── agents.conf           # nginx reverse proxy config
├── main.py                   # Updated chat UI, calls agents via HTTP
├── tools.py                  # Kept for backwards compat, imports from tools/
├── tests/
│   ├── test_config.py
│   ├── test_tools_filesystem.py
│   ├── test_tools_codesearch.py
│   ├── test_tools_web.py
│   ├── test_tools_marketplace.py
│   ├── test_agent_base.py
│   ├── test_agent_filesystem.py
│   ├── test_agent_codesearch.py
│   ├── test_agent_web.py
│   ├── test_agent_marketplace.py
│   └── test_dispatcher.py
└── pyproject.toml            # Add mcp[cli], httpx, pytest deps
```

---

## Chunk 1: Foundation — Config, Dependencies, Tool Modules

### Task 1: Add dependencies and create config module

**Files:**
- Modify: `pyproject.toml`
- Create: `config.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test — config module imports**

Create `tests/test_config.py`:

```python
"""Test that config module exists and has required constants."""


def test_config_ports():
    from config import AGENT_PORTS
    assert isinstance(AGENT_PORTS, dict)
    assert "filesystem" in AGENT_PORTS
    assert "codesearch" in AGENT_PORTS
    assert "web" in AGENT_PORTS
    assert "marketplace" in AGENT_PORTS
    assert "dispatcher" in AGENT_PORTS


def test_config_models():
    from config import AGENT_MODELS, AGENT_PORTS
    assert isinstance(AGENT_MODELS, dict)
    assert set(AGENT_MODELS.keys()) == set(AGENT_PORTS.keys())


def test_config_rate_limits():
    from config import RATE_LIMITS
    assert isinstance(RATE_LIMITS, dict)
    assert "ebay" in RATE_LIMITS
    assert "amazon" in RATE_LIMITS
    assert "craigslist" in RATE_LIMITS
    assert "default" in RATE_LIMITS
    assert all(isinstance(v, (int, float)) for v in RATE_LIMITS.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Update pyproject.toml with new dependencies**

Add to `pyproject.toml` dependencies:

```toml
[project]
name = "agentic-w-langchain-ollama"
version = "0.2.0"
description = "Multi-agent platform with LangChain + Ollama"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "flask>=3.1.2",
    "langchain>=1.2.10",
    "langchain-ollama>=1.0.1",
    "langgraph>=1.0.8",
    "ollama>=0.6.1",
    "mcp[cli]>=1.12.0",
    "httpx>=0.28.0",
    "pytest>=8.0.0",
]
```

- [ ] **Step 4: Install new dependencies**

Run: `uv sync` or `pip install -e .`

- [ ] **Step 5: Create config.py**

Create `config.py`:

```python
"""Central configuration for all agents."""

# Port assignments per agent
AGENT_PORTS = {
    "filesystem": 8101,
    "codesearch": 8102,
    "web": 8103,
    "marketplace": 8104,
    "dispatcher": 8105,
}

# Ollama model per agent — override with env vars or CLI args
AGENT_MODELS = {
    "filesystem": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "codesearch": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "web": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "marketplace": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "dispatcher": "huihui_ai/qwen2.5-coder-abliterate:14b",
}

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2

# Base URL for subagent HTTP calls (from dispatcher)
def agent_url(name: str) -> str:
    """Return the HTTP base URL for a named agent."""
    port = AGENT_PORTS[name]
    return f"http://127.0.0.1:{port}"
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 7: Create tests/conftest.py for path setup**

Create `tests/conftest.py`:

```python
"""Pytest configuration — ensure project root is on sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 8: Commit**

```bash
git add config.py tests/conftest.py tests/test_config.py pyproject.toml
git commit -m "feat: add config module and update dependencies for multi-agent architecture"
```

---

### Task 2: Split tools.py into tools/ package — filesystem module

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/filesystem.py`
- Test: `tests/test_tools_filesystem.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_tools_filesystem.py`:

```python
"""Test that filesystem tools are importable from the tools package."""
import os
import tempfile


def test_filesystem_tools_importable():
    from tools.filesystem import FILESYSTEM_TOOLS
    assert len(FILESYSTEM_TOOLS) == 13
    names = {t.name for t in FILESYSTEM_TOOLS}
    assert "read_file" in names
    assert "write_file" in names
    assert "tree" in names
    assert "grep" not in names  # grep belongs to codesearch


def test_read_file_works():
    from tools.filesystem import read_file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("line1\nline2\nline3\n")
        path = f.name
    try:
        result = read_file.invoke({"path": path})
        assert "line1" in result
        assert "line2" in result
    finally:
        os.unlink(path)


def test_write_file_works():
    from tools.filesystem import write_file
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.txt")
        result = write_file.invoke({"path": path, "content": "hello"})
        assert "Wrote" in result
        with open(path) as f:
            assert f.read() == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools_filesystem.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.filesystem'`

- [ ] **Step 3: Create tools/filesystem.py**

Extract lines 1-280 from `tools.py` into `tools/filesystem.py`. This includes:
- Imports: `os`, `re`, `glob as glob_mod`, `json`, `shutil`, `difflib` (only those needed)
- All functions from "Read Operations" section (lines 26-122): `read_file`, `file_info`, `list_dir`, `tree`
- All functions from "Write Operations" section (lines 124-219): `write_file`, `append_file`, `replace_in_file`, `insert_at_line`, `delete_lines`
- All functions from "File Management" section (lines 221-280): `copy_file`, `move_file`, `delete_file`, `make_dir`
- An `FILESYSTEM_TOOLS` list at the bottom

```python
"""Filesystem tools: read, write, edit, and manage files and directories."""

import os
import json
import glob as glob_mod
import shutil
from pathlib import Path

from langchain.tools import tool


# ── Read Operations ──────────────────────────────────────────────────────────

@tool
def read_file(path: str, start_line: int = 0, end_line: int = -1) -> str:
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
def file_info(path: str) -> str:
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
def list_dir(path: str = ".", recursive: bool = False, pattern: str = "*") -> str:
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
    """Generate a directory tree string.

    Args:
        path: Root directory.
        max_depth: Maximum depth to traverse.
        show_hidden: Include dotfiles/dotdirs.
    """
    path = os.path.expanduser(path)
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
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            full = os.path.join(dir_path, entry)
            lines.append(f"{prefix}{connector}{entry}")
            if os.path.isdir(full):
                ext = "    " if i == len(entries) - 1 else "│   "
                _walk(full, prefix + ext, depth + 1)

    lines.append(os.path.basename(path) or path)
    _walk(path, "  ", 1)
    return "\n".join(lines)


# ── Write Operations ─────────────────────────────────────────────────────────

@tool
def write_file(path: str, content: str) -> str:
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
def append_file(path: str, content: str) -> str:
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
def replace_in_file(path: str, old: str, new: str, count: int = 1) -> str:
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
def insert_at_line(path: str, line_number: int, content: str) -> str:
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
def delete_lines(path: str, start: int, end: int) -> str:
    """Delete a range of lines from a file (1-indexed, inclusive).

    Args:
        path: File to edit.
        start: First line to delete (1-indexed).
        end: Last line to delete (1-indexed, inclusive).
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    removed = lines[start - 1 : end]
    del lines[start - 1 : end]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Deleted lines {start}-{end} ({len(removed)} lines) from {os.path.abspath(path)}"


# ── File Management ──────────────────────────────────────────────────────────

@tool
def copy_file(src: str, dst: str) -> str:
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
def move_file(src: str, dst: str) -> str:
    """Move/rename a file or directory.

    Args:
        src: Source path.
        dst: Destination path.
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    shutil.move(src, dst)
    return f"Moved {src} -> {dst}"


@tool
def delete_file(path: str) -> str:
    """Delete a file or empty directory.

    Args:
        path: Path to delete.
    """
    path = os.path.expanduser(path)
    if os.path.isdir(path):
        os.rmdir(path)
    else:
        os.remove(path)
    return f"Deleted {os.path.abspath(path)}"


@tool
def make_dir(path: str) -> str:
    """Create a directory (and parents).

    Args:
        path: Directory path to create.
    """
    path = os.path.expanduser(path)
    os.makedirs(path, exist_ok=True)
    return f"Created directory {os.path.abspath(path)}"


# ── Registry ─────────────────────────────────────────────────────────────────

FILESYSTEM_TOOLS = [
    read_file,
    file_info,
    list_dir,
    tree,
    write_file,
    append_file,
    replace_in_file,
    insert_at_line,
    delete_lines,
    copy_file,
    move_file,
    delete_file,
    make_dir,
]
```

- [ ] **Step 4: Create empty tools/__init__.py**

```python
"""Tool registry — grouped by agent domain. Populated in Task 5."""
```

This is an empty placeholder so `tools/` is a valid package. The full `__init__.py` with all imports is created in Task 5 after all modules exist.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_tools_filesystem.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/filesystem.py tests/test_tools_filesystem.py
git commit -m "feat: extract filesystem tools into tools/filesystem module"
```

---

### Task 3: Split tools.py — codesearch module

**Files:**
- Create: `tools/codesearch.py`
- Test: `tests/test_tools_codesearch.py`

Source: lines 281-397 of current `tools.py` (grep, find_files, find_definition)

- [ ] **Step 1: Write failing test**

Create `tests/test_tools_codesearch.py`:

```python
"""Test that codesearch tools are importable and work."""
import os
import tempfile


def test_codesearch_tools_importable():
    from tools.codesearch import CODESEARCH_TOOLS
    assert len(CODESEARCH_TOOLS) == 3
    names = {t.name for t in CODESEARCH_TOOLS}
    assert names == {"grep", "find_files", "find_definition"}


def test_grep_works():
    from tools.codesearch import grep
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.py")
        with open(path, "w") as f:
            f.write("def hello():\n    return 'world'\n")
        result = grep.invoke({"pattern": "hello", "path": d})
        assert "hello" in result


def test_find_files_works():
    from tools.codesearch import find_files
    with tempfile.TemporaryDirectory() as d:
        for name in ["a.py", "b.py", "c.txt"]:
            open(os.path.join(d, name), "w").close()
        result = find_files.invoke({"pattern": "*.py", "path": d})
        assert "a.py" in result
        assert "b.py" in result
        assert "c.txt" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools_codesearch.py -v`
Expected: FAIL

- [ ] **Step 3: Create tools/codesearch.py**

Extract the "Search Operations" section (lines 281-397) from `tools.py`. Includes `grep`, `find_files`, `find_definition`. These functions use `os`, `re`, `glob as glob_mod`, `difflib` imports. Copy the exact function bodies from the current `tools.py`.

The file ends with:

```python
CODESEARCH_TOOLS = [
    grep,
    find_files,
    find_definition,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tools_codesearch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/codesearch.py tests/test_tools_codesearch.py
git commit -m "feat: extract code search tools into tools/codesearch module"
```

---

### Task 4: Split tools.py — web module

**Files:**
- Create: `tools/web.py`
- Test: `tests/test_tools_web.py`

Source: lines 399-454 of current `tools.py` (web_search, fetch_url)

- [ ] **Step 1: Write failing test**

Create `tests/test_tools_web.py`:

```python
"""Test that web tools are importable."""


def test_web_tools_importable():
    from tools.web import WEB_TOOLS
    assert len(WEB_TOOLS) == 2
    names = {t.name for t in WEB_TOOLS}
    assert names == {"web_search", "fetch_url"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools_web.py -v`
Expected: FAIL

- [ ] **Step 3: Create tools/web.py**

Extract lines 399-454 from `tools.py`. Includes `web_search`, `fetch_url`. Uses `urllib.request`, `urllib.parse`, `json`, `re` imports. Copy exact function bodies.

Ends with:

```python
WEB_TOOLS = [
    web_search,
    fetch_url,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tools_web.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/web.py tests/test_tools_web.py
git commit -m "feat: extract web tools into tools/web module"
```

---

### Task 5: Split tools.py — marketplace module

**Files:**
- Create: `tools/marketplace.py`
- Test: `tests/test_tools_marketplace.py`

Source: lines 456-1706 of current `tools.py`. This is the largest module. It includes:
- Constants: `EBAY_SORT_OPTIONS`, `DENVER_AREA_CITIES`, `ALL_CL_CITIES`
- Helper functions (not @tool): `_parse_ebay_listings`, `_extract_gpu_model`, `_parse_shipping_cost`, `_parse_amazon_listings`, `_parse_craigslist_listings`, `_craigslist_search_city`
- Tool functions: `ebay_search`, `ebay_sold_search`, `ebay_deep_scan`, `amazon_search`, `craigslist_search`, `craigslist_multi_search`
- Flow tools: `cross_platform_search`, `deal_finder`, `enrichment_pipeline`

**Important:** The flow tools (`cross_platform_search`, `deal_finder`, `enrichment_pipeline`) call other marketplace tools directly. They stay in this module for now but will later be owned by the dispatcher agent (Task 10).

- [ ] **Step 1: Write failing test**

Create `tests/test_tools_marketplace.py`:

```python
"""Test that marketplace tools are importable."""


def test_marketplace_tools_importable():
    from tools.marketplace import MARKETPLACE_TOOLS
    assert len(MARKETPLACE_TOOLS) == 6
    names = {t.name for t in MARKETPLACE_TOOLS}
    expected = {
        "ebay_search", "ebay_sold_search", "ebay_deep_scan",
        "amazon_search", "craigslist_search", "craigslist_multi_search",
    }
    assert names == expected


def test_flow_tools_separate():
    """Flow tools exist but are NOT in MARKETPLACE_TOOLS — they belong to the dispatcher."""
    from tools.marketplace import FLOW_TOOLS
    assert len(FLOW_TOOLS) == 3
    names = {t.name for t in FLOW_TOOLS}
    assert names == {"cross_platform_search", "deal_finder", "enrichment_pipeline"}


def test_ebay_sort_options():
    from tools.marketplace import EBAY_SORT_OPTIONS
    assert "best_match" in EBAY_SORT_OPTIONS
    assert "price_low" in EBAY_SORT_OPTIONS


def test_denver_area_cities():
    from tools.marketplace import CRAIGSLIST_DENVER_AREA
    assert "denver" in CRAIGSLIST_DENVER_AREA
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tools_marketplace.py -v`
Expected: FAIL

- [ ] **Step 3: Create tools/marketplace.py**

Extract lines 456-1706 from `tools.py`. This includes everything from `EBAY_SORT_OPTIONS` through `enrichment_pipeline`. Uses imports: `os`, `re`, `json`, `time`, `random`, `urllib.request`, `urllib.parse`, `langchain.tools.tool`, `langchain_ollama.ChatOllama`, `langchain_core.messages.HumanMessage`, `langchain_core.messages.SystemMessage`.

Ends with two separate registries — platform tools (for the marketplace agent) and flow tools (for the dispatcher):

```python
MARKETPLACE_TOOLS = [
    ebay_search,
    ebay_sold_search,
    ebay_deep_scan,
    amazon_search,
    craigslist_search,
    craigslist_multi_search,
]

# Flow tools call marketplace tools internally — owned by dispatcher, not marketplace agent
FLOW_TOOLS = [
    cross_platform_search,
    deal_finder,
    enrichment_pipeline,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tools_marketplace.py -v`
Expected: PASS

- [ ] **Step 5: Finalize tools/__init__.py and verify ALL_TOOLS**

Now that all 4 tool modules exist, replace `tools/__init__.py` with the full registry:

```python
"""Tool registry — grouped by agent domain."""

from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS, FLOW_TOOLS

ALL_TOOLS = FILESYSTEM_TOOLS + CODESEARCH_TOOLS + WEB_TOOLS + MARKETPLACE_TOOLS + FLOW_TOOLS
```

Run: `python -c "from tools import ALL_TOOLS; print(f'{len(ALL_TOOLS)} tools loaded'); assert len(ALL_TOOLS) == 27"`
Expected: `27 tools loaded` (13 + 3 + 2 + 6 + 3 = 27)

- [ ] **Step 6: Update old tools.py for backwards compat**

Replace the contents of the root `tools.py` with:

```python
"""Backwards compatibility — imports from tools/ package."""
from tools import ALL_TOOLS

__all__ = ["ALL_TOOLS"]
```

Verify main.py still works: `python -c "from tools import ALL_TOOLS; print(len(ALL_TOOLS))"`

- [ ] **Step 7: Commit**

```bash
git add tools/__init__.py tools/marketplace.py tests/test_tools_marketplace.py tools.py
git commit -m "feat: split monolithic tools.py into tools/ package with 4 domain modules"
```

---

## Chunk 2: Agent Base and Subagents

### Task 6: Create the agent base — shared MCP server factory

**Files:**
- Create: `agents/__init__.py`
- Create: `agents/base.py`
- Test: `tests/test_agent_base.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_agent_base.py`:

```python
"""Test the agent base factory."""
import asyncio
from mcp.server.fastmcp import FastMCP


def test_create_mcp_agent_returns_fastmcp():
    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[],
        system_prompt="You are a test agent.",
    )
    assert isinstance(app, FastMCP)


def test_create_mcp_agent_registers_tools():
    from langchain.tools import tool as lc_tool

    @lc_tool
    def dummy_tool(x: str) -> str:
        """A dummy tool."""
        return x

    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[dummy_tool],
        system_prompt="You are a test agent.",
    )
    # Use the public list_tools() coroutine to verify registration
    tools = asyncio.run(app.list_tools())
    tool_names = [t.name for t in tools]
    assert "dummy_tool" in tool_names


def test_prompt_discipline_included():
    from agents.base import PROMPT_DISCIPLINE
    assert "Do not speculate" in PROMPT_DISCIPLINE
    assert "Never describe the format" in PROMPT_DISCIPLINE


def test_system_prompt_stored_as_resource():
    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[],
        system_prompt="Custom prompt here.",
    )
    # System prompt is stored as an MCP resource for client retrieval
    resources = asyncio.run(app.list_resources())
    resource_uris = [str(r.uri) for r in resources]
    assert any("system-prompt" in uri for uri in resource_uris)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_base.py -v`
Expected: FAIL

- [ ] **Step 3: Create agents/__init__.py**

```python
"""Agent package."""
```

- [ ] **Step 4: Create agents/base.py**

```python
"""Shared factory for creating MCP agent servers.

Each subagent is a FastMCP server with streamable-http transport.
Tools are bridged from LangChain @tool functions to MCP tool handlers.
"""

import inspect
import typing

from mcp.server.fastmcp import FastMCP


PROMPT_DISCIPLINE = """You are a tool executor. You receive parameters, call tools, return raw structured results.

Rules:
- Do not speculate about user intent. Do not hypothesize motivations.
- Execute the request. Return the result.
- Never describe the format of data. Never describe what data looks like.
- Process data and return actionable output.
- No preamble. No analysis. No suggestions. No follow-up questions.
- Return JSON only when returning structured data.
- If you cannot process the request, return an error with what went wrong."""


def create_mcp_agent(
    name: str,
    tools: list,
    system_prompt: str = "",
    stateless: bool = True,
) -> FastMCP:
    """Create a FastMCP server with LangChain tools bridged to MCP tools.

    Args:
        name: Agent name (used in MCP server identification).
        tools: List of LangChain @tool decorated functions.
        system_prompt: Additional system prompt (appended to prompt discipline).
        stateless: If True, use stateless HTTP mode (recommended).

    Returns:
        Configured FastMCP instance ready to run.
    """
    full_prompt = PROMPT_DISCIPLINE
    if system_prompt:
        full_prompt += "\n\n" + system_prompt

    mcp = FastMCP(
        name,
        stateless_http=stateless,
        json_response=True,
    )

    # Bridge each LangChain tool to an MCP tool
    for lc_tool in tools:
        _register_lc_tool(mcp, lc_tool)

    # Health check as a simple HTTP-accessible resource
    @mcp.resource(f"health://{name}")
    def health() -> str:
        return f'{{"status": "ok", "agent": "{name}", "tools": {len(tools)}}}'

    # Store the system prompt as a retrievable MCP resource
    @mcp.resource(f"config://system-prompt/{name}")
    def get_system_prompt() -> str:
        return full_prompt

    return mcp


def _register_lc_tool(mcp: FastMCP, lc_tool) -> None:
    """Bridge a LangChain tool to an MCP tool handler.

    Extracts name, description, and schema from the LangChain tool
    and registers an equivalent MCP tool that delegates to lc_tool.invoke().
    Uses model_json_schema() (Pydantic v2) and preserves default values.
    """
    tool_name = lc_tool.name
    tool_desc = lc_tool.description or ""

    # Extract the parameter schema from LangChain tool (Pydantic v2)
    schema = lc_tool.args_schema.model_json_schema() if lc_tool.args_schema else {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build parameter list with types and defaults
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    # Build inspect.Parameter objects for proper function signature
    params_list = []
    for pname, pinfo in properties.items():
        ptype = pinfo.get("type", "string")
        py_type = type_map.get(ptype, str)

        if pname in required:
            param = inspect.Parameter(
                pname,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=py_type,
            )
        else:
            default = pinfo.get("default")
            param = inspect.Parameter(
                pname,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=typing.Optional[py_type],
            )
        params_list.append(param)

    # Create an MCP tool function that delegates to the LangChain tool
    def make_handler(lt, sig):
        async def handler(**kwargs) -> str:
            # Remove None values for optional params not provided
            cleaned = {k: v for k, v in kwargs.items() if v is not None}
            result = lt.invoke(cleaned)
            return str(result)

        handler.__name__ = tool_name
        handler.__doc__ = tool_desc
        handler.__signature__ = sig
        return handler

    sig = inspect.Signature(
        parameters=params_list,
        return_annotation=str,
    )
    handler = make_handler(lc_tool, sig)
    mcp.tool()(handler)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_base.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agents/ tests/test_agent_base.py
git commit -m "feat: add agent base factory bridging LangChain tools to MCP servers"
```

---

### Task 7: Create filesystem agent

**Files:**
- Create: `agents/filesystem.py`
- Test: `tests/test_agent_filesystem.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_agent_filesystem.py`:

```python
"""Test filesystem agent creation."""
from mcp.server.fastmcp import FastMCP


def test_filesystem_agent_creates():
    from agents.filesystem import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "filesystem-agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_filesystem.py -v`
Expected: FAIL

- [ ] **Step 3: Create agents/filesystem.py**

```python
"""Filesystem agent — MCP server for file read/write/manage operations.

Port: 8101
Tools: 13 filesystem tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.filesystem import FILESYSTEM_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Execute filesystem operations exactly as requested.
Return raw file contents, directory listings, or operation confirmations.
No commentary on file contents. No suggestions about what to do next."""


def create_app():
    return create_mcp_agent(
        name="filesystem-agent",
        tools=FILESYSTEM_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["filesystem"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_filesystem.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/filesystem.py tests/test_agent_filesystem.py
git commit -m "feat: add filesystem MCP agent server"
```

---

### Task 8: Create codesearch and web agents

**Files:**
- Create: `agents/codesearch.py`
- Create: `agents/web.py`
- Test: `tests/test_agent_codesearch.py`
- Test: `tests/test_agent_web.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_agent_codesearch.py`:

```python
"""Test codesearch agent creation."""
from mcp.server.fastmcp import FastMCP


def test_codesearch_agent_creates():
    from agents.codesearch import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "codesearch-agent"
```

Create `tests/test_agent_web.py`:

```python
"""Test web agent creation."""
from mcp.server.fastmcp import FastMCP


def test_web_agent_creates():
    from agents.web import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "web-agent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent_codesearch.py tests/test_agent_web.py -v`
Expected: FAIL

- [ ] **Step 3: Create agents/codesearch.py**

```python
"""Code search agent — MCP server for grep, find, definition lookup.

Port: 8102
Tools: 3 code search tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.codesearch import CODESEARCH_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Search code and return matching results with full file paths and line numbers.
Return raw search results. No interpretation of what the code does.
No suggestions about code quality or improvements."""


def create_app():
    return create_mcp_agent(
        name="codesearch-agent",
        tools=CODESEARCH_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["codesearch"])
```

- [ ] **Step 4: Create agents/web.py**

```python
"""Web agent — MCP server for web search and URL fetching.

Port: 8103
Tools: 2 web tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.web import WEB_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Fetch web content and return raw results.
Return the actual text/data from web pages. No summarization.
If a page fails to load, return the error. Do not speculate about why."""


def create_app():
    return create_mcp_agent(
        name="web-agent",
        tools=WEB_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["web"])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent_codesearch.py tests/test_agent_web.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agents/codesearch.py agents/web.py tests/test_agent_codesearch.py tests/test_agent_web.py
git commit -m "feat: add codesearch and web MCP agent servers"
```

---

### Task 9: Create marketplace agent

**Files:**
- Create: `agents/marketplace.py`
- Test: `tests/test_agent_marketplace.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_agent_marketplace.py`:

```python
"""Test marketplace agent creation."""
from mcp.server.fastmcp import FastMCP


def test_marketplace_agent_creates():
    from agents.marketplace import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "marketplace-agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_marketplace.py -v`
Expected: FAIL

- [ ] **Step 3: Create agents/marketplace.py**

```python
"""Marketplace agent — MCP server for eBay, Amazon, Craigslist searches.

Port: 8104
Tools: 6 platform search tools (flow tools are owned by the dispatcher)
Model: medium abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.marketplace import MARKETPLACE_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Search marketplace platforms and return structured listing data.
Every listing MUST include: title, price, shipping, url, platform.
Return results as JSON arrays. No analysis. No filtering. No opinions.
No commentary about what the listings mean or whether they are good deals."""


def create_app():
    return create_mcp_agent(
        name="marketplace-agent",
        tools=MARKETPLACE_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["marketplace"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_marketplace.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/marketplace.py tests/test_agent_marketplace.py
git commit -m "feat: add marketplace MCP agent server"
```

---

## Chunk 3: Dispatcher Agent

### Task 10: Create the dispatcher/analyst agent

**Files:**
- Create: `agents/dispatcher.py`
- Test: `tests/test_dispatcher.py`

This is the most complex agent. It:
1. Has tool definitions loaded (from all tool modules) for planning, but never calls them directly
2. Calls subagents via httpx HTTP client
3. Evaluates result quality via LLM self-eval
4. Retries on bad data (max 2 retries)
5. Applies rate limiting (parallel across platforms, sequential within platform)

- [ ] **Step 1: Write failing test**

Create `tests/test_dispatcher.py`:

```python
"""Test dispatcher agent components."""
import asyncio


def test_dispatcher_importable():
    from agents.dispatcher import create_app
    from mcp.server.fastmcp import FastMCP
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "dispatcher-agent"


def test_rate_limiter():
    from agents.dispatcher import PlatformRateLimiter
    limiter = PlatformRateLimiter()

    async def check():
        # First call should not wait
        import time
        start = time.monotonic()
        await limiter.acquire("ebay")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # First call is instant

    asyncio.run(check())


def test_classify_platform():
    from agents.dispatcher import classify_platform
    assert classify_platform("ebay_search") == "ebay"
    assert classify_platform("ebay_sold_search") == "ebay"
    assert classify_platform("ebay_deep_scan") == "ebay"
    assert classify_platform("amazon_search") == "amazon"
    assert classify_platform("craigslist_search") == "craigslist"
    assert classify_platform("craigslist_multi_search") == "craigslist"
    assert classify_platform("web_search") == "other"


def test_tool_registry_loaded():
    from agents.dispatcher import TOOL_REGISTRY
    assert len(TOOL_REGISTRY) > 0
    # Check it has tool metadata, not actual tool objects
    first = TOOL_REGISTRY[0]
    assert "name" in first
    assert "description" in first
    assert "params" in first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dispatcher.py -v`
Expected: FAIL

- [ ] **Step 3: Create agents/dispatcher.py**

```python
"""Dispatcher/analyst agent — orchestrates subagents and does all reasoning.

Port: 8105
Tools: None directly (has tool definitions for planning)
Model: strongest available abliterated model

The dispatcher:
1. Receives user requests via MCP
2. Plans which subagents to call with what parameters
3. Fans out requests (parallel across platforms, sequential within)
4. Evaluates result quality via LLM self-eval
5. Retries on bad data (max 2 retries)
6. Analyzes, deduplicates, ranks, presents results
"""

import asyncio
import json
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

from config import AGENT_PORTS, RATE_LIMITS, MAX_RETRIES, agent_url, AGENT_MODELS
from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS


# ── Tool registry (metadata only, for planning) ──────────────────────────────

def _tool_meta(t) -> dict:
    """Extract name, description, and parameter info from a LangChain tool."""
    schema = t.args_schema.model_json_schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            params[pname]["default"] = pinfo["default"]
    return {
        "name": t.name,
        "description": t.description.split("\n")[0] if t.description else "",
        "params": params,
    }


# Map tool names to which agent owns them
TOOL_TO_AGENT = {}
for t in FILESYSTEM_TOOLS:
    TOOL_TO_AGENT[t.name] = "filesystem"
for t in CODESEARCH_TOOLS:
    TOOL_TO_AGENT[t.name] = "codesearch"
for t in WEB_TOOLS:
    TOOL_TO_AGENT[t.name] = "web"
for t in MARKETPLACE_TOOLS:
    TOOL_TO_AGENT[t.name] = "marketplace"

ALL_AGENT_TOOLS = FILESYSTEM_TOOLS + CODESEARCH_TOOLS + WEB_TOOLS + MARKETPLACE_TOOLS
TOOL_REGISTRY = [_tool_meta(t) for t in ALL_AGENT_TOOLS]


# ── Platform classification ──────────────────────────────────────────────────

def classify_platform(tool_name: str) -> str:
    """Classify a tool name into its rate-limit platform group."""
    if tool_name.startswith("ebay"):
        return "ebay"
    if tool_name.startswith("amazon"):
        return "amazon"
    if tool_name.startswith("craigslist"):
        return "craigslist"
    return "other"


# ── Rate limiter ─────────────────────────────────────────────────────────────

class PlatformRateLimiter:
    """Enforces per-platform cooldowns between requests."""

    def __init__(self):
        self._last_call: dict[str, float] = {}
        # Pre-initialize all known platform locks to avoid race conditions
        self._locks: dict[str, asyncio.Lock] = {
            "ebay": asyncio.Lock(),
            "amazon": asyncio.Lock(),
            "craigslist": asyncio.Lock(),
            "other": asyncio.Lock(),
        }

    def _get_lock(self, platform: str) -> asyncio.Lock:
        if platform not in self._locks:
            self._locks[platform] = asyncio.Lock()
        return self._locks[platform]

    async def acquire(self, platform: str) -> None:
        """Wait until the cooldown for this platform has elapsed."""
        lock = self._get_lock(platform)
        async with lock:
            cooldown = RATE_LIMITS.get(platform, RATE_LIMITS["default"])
            last = self._last_call.get(platform, 0)
            elapsed = time.monotonic() - last
            if elapsed < cooldown:
                await asyncio.sleep(cooldown - elapsed)
            self._last_call[platform] = time.monotonic()


# ── Subagent MCP client ──────────────────────────────────────────────────────

async def call_subagent(
    agent_name: str,
    tool_name: str,
    params: dict,
    rate_limiter: PlatformRateLimiter,
) -> dict:
    """Call a subagent's tool via the MCP client library.

    Uses streamable_http_client to connect to the subagent's MCP server
    and call tools through the proper MCP protocol.

    Args:
        agent_name: Name of the agent (e.g., "marketplace")
        tool_name: Name of the tool to invoke
        params: Tool parameters

    Returns:
        {"status": "ok", "data": ..., "tool": tool_name} or
        {"status": "error", "error": ..., "tool": tool_name}
    """
    platform = classify_platform(tool_name)
    if platform != "other":
        await rate_limiter.acquire(platform)

    base_url = agent_url(agent_name)
    try:
        async with streamable_http_client(f"{base_url}/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=params)

                # Extract text content from MCP result
                data = ""
                for item in result.content:
                    if item.type == "text":
                        data = item.text
                        break

                return {"status": "ok", "data": data, "tool": tool_name}

    except Exception as e:
        return {"status": "error", "error": str(e), "tool": tool_name}


# ── Dispatcher system prompt ─────────────────────────────────────────────────

DISPATCHER_SYSTEM_PROMPT = """You are a dispatcher/analyst agent. You orchestrate specialized subagents to gather data, then analyze and present results.

## Your role
- You have knowledge of all available tools across all agents (see TOOL_REGISTRY below).
- Plan which agents to call with what parameters.
- When results come back, evaluate quality.
- When presenting final results to the user, extract and present the actual data.

## Rules
- Never describe data formats. Never speculate about intent.
- Never ask clarifying questions you can resolve yourself.
- Do not summarize tool results — extract the actual data and present it.
- If given data to analyze, analyze it. If given data to search, search it.
- If results are empty or garbage, say so in one sentence.

## Available tools (for planning — you delegate execution):
{tool_list}

## Marketplace tool selection
- ebay_search: Quick single-page eBay lookup
- ebay_sold_search: eBay completed/sold listings for market prices
- ebay_deep_scan: Multi-page paginated eBay scan with GPU model extraction
- amazon_search: Search Amazon product listings
- craigslist_search: Search one Craigslist city
- craigslist_multi_search: Search multiple Craigslist cities

## Rate limiting
- Requests to the same platform (eBay, Amazon, Craigslist) are sequential with cooldowns.
- Requests to different platforms run in parallel.

## GPU generations reference
Only consider Turing (2018) or newer for AI/ML relevance:
- Turing: RTX 2060/2070/2080, GTX 1650/1660, T4
- Ampere: RTX 3060/3070/3080/3090, A100/A40/A6000
- Ada Lovelace: RTX 4060/4070/4080/4090, L40/L40S
- Hopper: H100, H200
- Blackwell: RTX 5070/5080/5090, B100/B200/GB200

## eBay price analysis rules
1. Group by exact GPU model
2. Compute per-group median (not mean)
3. Flag as underpriced only if >=20% below median AND group has >=3 listings
4. Always add shipping to price before comparing
5. Show: model, total price, group median, % below median, URL
6. If no deals found, say so explicitly

## Craigslist fulfillment
- Denver area (pickup OK): denver, boulder, colorado springs, fort collins, pueblo
- All other cities: shipping required
"""


# ── MCP server creation ──────────────────────────────────────────────────────

def create_app():
    # Format tool list for the system prompt
    tool_list = "\n".join(
        f"- {t['name']}: {t['description']}"
        for t in TOOL_REGISTRY
    )
    prompt = DISPATCHER_SYSTEM_PROMPT.format(tool_list=tool_list)

    mcp = FastMCP(
        "dispatcher-agent",
        stateless_http=True,
        json_response=True,
    )

    rate_limiter = PlatformRateLimiter()

    @mcp.tool()
    async def dispatch(
        tool_name: str,
        params: str = "{}",
    ) -> str:
        """Call a subagent tool by name with JSON params.

        Args:
            tool_name: Name of the tool to invoke (e.g., "ebay_search")
            params: JSON string of tool parameters
        """
        if tool_name not in TOOL_TO_AGENT:
            return json.dumps({"status": "error", "error": f"Unknown tool: {tool_name}"})

        agent_name = TOOL_TO_AGENT[tool_name]
        try:
            parsed_params = json.loads(params) if isinstance(params, str) else params
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"Invalid params JSON: {e}"})

        result = await call_subagent(agent_name, tool_name, parsed_params, rate_limiter)
        return json.dumps(result)

    @mcp.tool()
    async def dispatch_parallel(
        requests: str,
    ) -> str:
        """Call multiple subagent tools in parallel (respecting rate limits).

        Args:
            requests: JSON array of {"tool": "name", "params": {...}} objects.
                      Tools on different platforms run in parallel.
                      Tools on the same platform run sequentially with cooldown.
        """
        try:
            req_list = json.loads(requests)
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"Invalid JSON: {e}"})

        # Group by platform for parallel execution
        platform_groups: dict[str, list] = {}
        for req in req_list:
            tool_name = req.get("tool", "")
            platform = classify_platform(tool_name)
            platform_groups.setdefault(platform, []).append(req)

        async def run_platform_group(reqs):
            """Run a group of same-platform requests sequentially."""
            results = []
            for req in reqs:
                tool_name = req.get("tool", "")
                params = req.get("params", {})
                agent_name = TOOL_TO_AGENT.get(tool_name)
                if not agent_name:
                    results.append({"status": "error", "error": f"Unknown tool: {tool_name}", "tool": tool_name})
                    continue
                result = await call_subagent(agent_name, tool_name, params, rate_limiter)
                results.append(result)
            return results

        # Run all platform groups in parallel
        tasks = [run_platform_group(reqs) for reqs in platform_groups.values()]
        group_results = await asyncio.gather(*tasks)

        # Flatten results
        all_results = []
        for group in group_results:
            all_results.extend(group)

        return json.dumps(all_results)

    @mcp.tool()
    async def check_quality(
        data: str,
        expected_format: str = "marketplace_listings",
    ) -> str:
        """Evaluate the quality of data returned by a subagent.

        Uses LLM self-eval to determine if the data is valid or garbage.

        Args:
            data: The data string to evaluate
            expected_format: What kind of data this should be
                           (e.g., "marketplace_listings", "file_contents", "search_results")
        """
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage

        model = AGENT_MODELS.get("dispatcher", "huihui_ai/qwen2.5-coder-abliterate:14b")
        llm = ChatOllama(model=model, temperature=0, base_url="http://localhost:11434")

        eval_prompt = f"""Evaluate this data. Expected format: {expected_format}.

Is this valid, usable data? Reply with ONLY a JSON object:
{{"valid": true/false, "reason": "brief explanation", "suggestion": "how to fix if invalid"}}

Data to evaluate:
{data[:2000]}"""

        result = llm.invoke([
            SystemMessage(content="You are a data quality evaluator. Return ONLY valid JSON. No other text."),
            HumanMessage(content=eval_prompt),
        ])
        return result.content

    return mcp


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["dispatcher"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dispatcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/dispatcher.py tests/test_dispatcher.py
git commit -m "feat: add dispatcher/analyst agent with rate limiting and quality eval"
```

---

## Chunk 4: nginx Config, Chat UI Update, and Launch Scripts

### Task 11: Create nginx reverse proxy config

**Files:**
- Create: `nginx/agents.conf`

- [ ] **Step 1: Create nginx/agents.conf**

```nginx
# Agentic subagent reverse proxy
# Include this in your nginx config: include /path/to/agents.conf;
# Or symlink to /etc/nginx/sites-enabled/

upstream filesystem_agent {
    server 127.0.0.1:8101;
}
upstream codesearch_agent {
    server 127.0.0.1:8102;
}
upstream web_agent {
    server 127.0.0.1:8103;
}
upstream marketplace_agent {
    server 127.0.0.1:8104;
}
upstream dispatcher_agent {
    server 127.0.0.1:8105;
}

server {
    listen 8100;
    server_name localhost;

    # Health check
    location /health {
        return 200 '{"status": "ok", "agents": ["filesystem","codesearch","web","marketplace","dispatcher"]}';
        add_header Content-Type application/json;
    }

    # Agent endpoints
    location /agents/filesystem/ {
        proxy_pass http://filesystem_agent/;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
    }

    location /agents/codesearch/ {
        proxy_pass http://codesearch_agent/;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
    }

    location /agents/web/ {
        proxy_pass http://web_agent/;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
    }

    location /agents/marketplace/ {
        proxy_pass http://marketplace_agent/;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
    }

    location /agents/dispatcher/ {
        proxy_pass http://dispatcher_agent/;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

- [ ] **Step 2: Verify nginx config syntax**

Run: `nginx -t -c $(pwd)/nginx/agents.conf 2>&1 || echo "Note: standalone syntax check may fail without full nginx.conf — verify after including in your nginx setup"`

- [ ] **Step 3: Commit**

```bash
git add nginx/agents.conf
git commit -m "feat: add nginx reverse proxy config for agent endpoints"
```

---

### Task 12: Update main.py to call agents via HTTP

**Files:**
- Modify: `main.py`

The chat UI keeps its Flask server but `_build_agent()` is updated to optionally route through the dispatcher agent via HTTP instead of building a monolithic LangGraph agent locally.

- [ ] **Step 1: Update _build_agent and add agent client mode**

In `main.py`, add an import for `httpx` and `config`, and add a new endpoint `/api/agent/call` that proxies requests to individual agents. Keep the existing monolithic mode as a fallback (when agents aren't running).

Add after the existing imports:

```python
import httpx
from config import AGENT_PORTS, agent_url
```

Add a new route for proxying to agents:

```python
@app.route("/api/agent/<agent_name>/call", methods=["POST"])
def call_agent(agent_name: str):
    """Proxy a tool call to a specific agent.

    Body: {"tool": "tool_name", "params": {...}}
    """
    if agent_name not in AGENT_PORTS:
        return jsonify({"error": f"Unknown agent: {agent_name}"}), 404

    data = request.get_json(force=True)
    tool_name = data.get("tool", "")
    params = data.get("params", {})

    try:
        url = agent_url(agent_name)
        resp = httpx.post(
            f"{url}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
                "id": 1,
            },
            timeout=60.0,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents", methods=["GET"])
def list_agents():
    """List all available agents and their status.

    Note: Uses synchronous httpx which blocks the Flask worker thread.
    Acceptable for dev; for production, use Quart or a threaded server.
    """
    agents = {}
    for name, port in AGENT_PORTS.items():
        try:
            # POST to /mcp with tools/list to check if agent is responding
            resp = httpx.post(
                f"http://127.0.0.1:{port}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                timeout=2.0,
            )
            resp.raise_for_status()
            agents[name] = {"port": port, "status": "up"}
        except Exception:
            agents[name] = {"port": port, "status": "down"}
    return jsonify(agents)
```

- [ ] **Step 2: Verify main.py still starts**

Run: `python main.py --serve &` then `curl http://localhost:5000/api/agents` then kill the server.
Expected: Returns JSON with agent statuses (all "down" since agents aren't running yet).

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add agent proxy endpoints to chat UI"
```

---

### Task 13: Create launch script

**Files:**
- Create: `run_agents.py`

- [ ] **Step 1: Create run_agents.py**

```python
"""Launch all agent MCP servers.

Usage:
    python run_agents.py              # Start all agents
    python run_agents.py filesystem   # Start only filesystem agent
    python run_agents.py marketplace dispatcher  # Start specific agents
"""

import os
import subprocess
import sys
import signal
import time

from config import AGENT_PORTS

AGENT_SCRIPTS = {
    "filesystem": os.path.join("agents", "filesystem.py"),
    "codesearch": os.path.join("agents", "codesearch.py"),
    "web": os.path.join("agents", "web.py"),
    "marketplace": os.path.join("agents", "marketplace.py"),
    "dispatcher": os.path.join("agents", "dispatcher.py"),
}


def main():
    agents_to_start = sys.argv[1:] if len(sys.argv) > 1 else list(AGENT_SCRIPTS.keys())
    processes = []

    for name in agents_to_start:
        if name not in AGENT_SCRIPTS:
            print(f"Unknown agent: {name}")
            print(f"Available: {', '.join(AGENT_SCRIPTS.keys())}")
            sys.exit(1)

    print(f"Starting {len(agents_to_start)} agent(s)...")

    for name in agents_to_start:
        script = AGENT_SCRIPTS[name]
        port = AGENT_PORTS[name]
        print(f"  {name:15s} -> http://127.0.0.1:{port}")
        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append((name, proc))
        time.sleep(0.5)  # Stagger startup

    print(f"\nAll agents started. Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        print("\nShutting down agents...")
        for name, proc in processes:
            proc.terminate()
            print(f"  Stopped {name}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for any process to exit
    while True:
        for name, proc in processes:
            ret = proc.poll()
            if ret is not None:
                print(f"\n  Agent {name} exited with code {ret}")
                stderr = proc.stderr.read().decode() if proc.stderr else ""
                if stderr:
                    print(f"  stderr: {stderr[:500]}")
        time.sleep(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test launching a single agent**

Run: `python run_agents.py filesystem`
Expected: Starts filesystem agent on port 8101. Ctrl+C to stop.

Run: `curl http://127.0.0.1:8101/mcp -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'`
Expected: JSON response listing filesystem tools.

- [ ] **Step 3: Commit**

```bash
git add run_agents.py
git commit -m "feat: add agent launcher script"
```

---

### Task 14: Integration test — full stack

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
"""Integration test — verifies the full agent stack.

Requires agents to be running. Skip if not available.
Run with: python run_agents.py & pytest tests/test_integration.py -v
"""
import asyncio
import os
import tempfile

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def agent_available(port: int) -> bool:
    """Check if an MCP agent is responding on the given port."""
    async def check():
        try:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                read_stream, write_stream, _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return True
        except Exception:
            return False
    return asyncio.run(check())


@pytest.fixture(autouse=True)
def skip_if_no_agents():
    if not agent_available(8101):
        pytest.skip("Agents not running — start with: python run_agents.py")


def test_filesystem_agent_lists_tools():
    async def run():
        async with streamable_http_client("http://127.0.0.1:8101/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "read_file" in names
                assert "write_file" in names
    asyncio.run(run())


def test_filesystem_agent_read_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content\n")
        path = f.name
    try:
        async def run():
            async with streamable_http_client("http://127.0.0.1:8101/mcp") as (
                read_stream, write_stream, _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool("read_file", arguments={"path": path})
                    text = result.content[0].text
                    assert "test content" in text
        asyncio.run(run())
    finally:
        os.unlink(path)


def test_dispatcher_lists_tools():
    if not agent_available(8105):
        pytest.skip("Dispatcher not running")

    async def run():
        async with streamable_http_client("http://127.0.0.1:8105/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "dispatch" in names
                assert "dispatch_parallel" in names
                assert "check_quality" in names
    asyncio.run(run())
```

- [ ] **Step 2: Run with agents started**

In one terminal: `python run_agents.py`
In another: `python -m pytest tests/test_integration.py -v`
Expected: PASS (or SKIP if agents not running)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: add integration tests for agent stack"
```

---

### Task 15: Final — update tools/__init__.py, verify backwards compat, final commit

- [ ] **Step 1: Verify all unit tests pass**

Run: `python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: All PASS

- [ ] **Step 2: Verify main.py still works with old import**

Run: `python -c "from tools import ALL_TOOLS; print(f'OK: {len(ALL_TOOLS)} tools')"`
Expected: `OK: 27 tools`

- [ ] **Step 3: Verify agents start**

Run: `python run_agents.py` — all 5 agents should start on ports 8101-8105.

- [ ] **Step 4: Final commit (if any uncommitted changes remain)**

```bash
git status
# Only add specific files that are new/modified — do NOT use git add -A
# Verify .gitignore covers __pycache__/, .pyc, .env, etc. before committing
git commit -m "feat: complete multi-agent architecture with MCP subagents and dispatcher"
```
