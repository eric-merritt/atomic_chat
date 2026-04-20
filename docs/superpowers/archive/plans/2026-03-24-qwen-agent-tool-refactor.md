# Qwen-Agent Tool Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all LangChain tool definitions and the manual tool-calling loop with qwen-agent's `BaseTool`/`@register_tool` pattern and `Assistant.run()` agent loop.

**Architecture:** Each `@tool`-decorated function becomes a `BaseTool` subclass with `@register_tool`. The manual `parse_tool_calls()` + streaming loop in `main.py` is replaced by qwen-agent's `Assistant` which handles tool-call parsing, execution, and multi-round loops natively. The 1.7B workers (`task_extractor.py`, `tool_curator.py`) switch from `ChatOllama` to qwen-agent LLM config with `model_type: 'oai'` pointing at Ollama's OpenAI-compatible endpoint.

**Tech Stack:** qwen-agent, json5, Flask, SQLAlchemy, Ollama (via OpenAI-compatible API at `localhost:11434/v1`)

---

## File Structure

### New files
- `tests/test_tools_filesystem.py` — unit tests for converted filesystem tools
- `tests/test_tools_codesearch.py` — unit tests for converted code search tools
- `tests/test_tools_web.py` — unit tests for converted web tools
- `tests/test_tools_ecommerce.py` — unit tests for converted ecommerce tools
- `tests/test_tools_onlyfans.py` — unit tests for converted onlyfans tools
- `tests/test_tools_torrent.py` — unit tests for converted torrent tools
- `tests/test_tools_mcp.py` — unit tests for converted mcp tools
- `tests/test_tools_accounting.py` — unit tests for converted accounting tools
- `tests/test_tool_output.py` — unit tests for updated `_output.py`
- `tests/test_context.py` — unit tests for converted context module
- `tests/test_task_extractor.py` — unit tests for qwen-agent task extractor
- `tests/test_tool_curator.py` — unit tests for qwen-agent tool curator
- `tests/test_main_chat.py` — unit tests for the refactored chat pipeline

### Modified files
- `tools/_output.py` — update `tool_result()` to return dict instead of JSON string
- `tools/filesystem.py` — convert 12 tools from `@tool` to `@register_tool` + `BaseTool`
- `tools/codesearch.py` — convert 3 tools
- `tools/web.py` — convert 7 tools
- `tools/ecommerce.py` — convert ~9 tools
- `tools/onlyfans.py` — convert ~6 tools
- `tools/torrent.py` — convert ~6 tools
- `tools/mcp.py` — convert 1 tool
- `tools/accounting.py` — convert 21 tools
- `tools/__init__.py` — replace manual list aggregation with import-only auto-registration
- `context.py` — remove LangChain message types, use qwen-agent message dicts
- `task_extractor.py` — replace `ChatOllama` with qwen-agent LLM config
- `tool_curator.py` — replace `ChatOllama` with qwen-agent LLM config
- `main.py` — replace `_tool_meta()`, `parse_tool_calls()`, `_get_llm()`, tool loop with `Assistant.run()`
- `workflow_groups.py` — update to use qwen-agent registry for tool lookup
- `config.py` — add qwen-agent LLM config builder
- `pyproject.toml` — add `qwen-agent` and `json5` dependencies
- `routes/tools.py` — update tool metadata extraction

### Deleted code (within files)
- `main.py`: `_tool_meta()`, `parse_tool_calls()`, `_get_llm()`, `_TOOL_BY_NAME`, manual tool-call loop
- `context.py`: LangChain message imports and conversion functions
- All files: `from langchain.tools import tool` imports

---

## Task 1: Add qwen-agent dependency and verify install

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add qwen-agent and json5 to dependencies**

```toml
# In pyproject.toml [project] dependencies, add:
    "qwen-agent>=0.1.0",
    "json5>=0.10.0",
```

Add these two lines after the existing `"requests>=2.32.5",` line.

- [ ] **Step 2: Install dependencies**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv sync`
Expected: Dependencies install successfully, including qwen-agent and json5.

- [ ] **Step 3: Verify qwen-agent imports**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run python -c "from qwen_agent.tools.base import BaseTool, register_tool; import json5; print('OK')"`
Expected: Prints "OK"

- [ ] **Step 4: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add pyproject.toml uv.lock
git commit -m "chore: add qwen-agent and json5 dependencies"
```

---

## Task 2: Update `_output.py` — return dicts instead of JSON strings

qwen-agent tools return `Union[str, list, dict]` and the agent converts to string automatically. Our `tool_result()` currently returns a JSON string. Change it to return a dict.

**Files:**
- Modify: `tools/_output.py`
- Create: `tests/test_tool_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tool_output.py
"""Tests for tools._output module."""

import pytest
from tools._output import tool_result, retry


class TestToolResult:
    def test_success_returns_dict(self):
        result = tool_result(data={"key": "value"})
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["data"] == {"key": "value"}
        assert result["error"] == ""

    def test_error_returns_dict(self):
        result = tool_result(error="something broke")
        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert result["data"] is None
        assert result["error"] == "something broke"

    def test_no_args_returns_success_with_none_data(self):
        result = tool_result()
        assert result["status"] == "success"
        assert result["data"] is None


class TestRetry:
    def test_succeeds_first_try(self):
        @retry(max_retries=3)
        def ok():
            return "done"
        assert ok() == "done"

    def test_retries_on_failure(self):
        call_count = 0
        @retry(max_retries=3, delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"
        assert flaky() == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        @retry(max_retries=2, delay=0.01)
        def always_fail():
            raise ConnectionError("fail")
        with pytest.raises(ConnectionError):
            always_fail()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tool_output.py -v`
Expected: `TestToolResult` tests FAIL because `tool_result()` returns a string, not a dict. `TestRetry` tests may pass.

- [ ] **Step 3: Update `tool_result()` to return dict**

Replace the `tool_result` function in `tools/_output.py`:

```python
def tool_result(data=None, error: str = "") -> dict:
    """Return a standardized result dict.

    All tools MUST return the output of this function.
    qwen-agent converts dict returns to string automatically.

    Args:
        data: The tool's result payload. Any JSON-serializable value.
        error: Error message. If non-empty, status is "error".

    Returns:
        Dict: {"status": "success"|"error", "data": ..., "error": ""}
    """
    if error:
        return {"status": "error", "data": None, "error": error}
    return {"status": "success", "data": data, "error": ""}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tool_output.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/_output.py tests/test_tool_output.py
git commit -m "refactor: tool_result returns dict instead of JSON string for qwen-agent compatibility"
```

---

## Task 3: Convert filesystem tools to qwen-agent BaseTool

Convert all 12 tools in `tools/filesystem.py` from `@tool` decorator pattern to `@register_tool` + `BaseTool` subclass pattern.

**Files:**
- Modify: `tools/filesystem.py`
- Create: `tests/test_tools_filesystem.py`

- [ ] **Step 1: Write failing tests for 3 representative tools (read, write, ls)**

```python
# tests/test_tools_filesystem.py
"""Tests for qwen-agent filesystem tools."""

import os
import json
import json5
import tempfile
import pytest

from qwen_agent.tools.base import BaseTool, TOOL_REGISTRY


class TestFilesystemToolRegistration:
    """Verify tools are registered in qwen-agent's global registry."""

    def test_read_registered(self):
        assert 'read' in TOOL_REGISTRY

    def test_write_registered(self):
        assert 'write' in TOOL_REGISTRY

    def test_ls_registered(self):
        assert 'ls' in TOOL_REGISTRY

    def test_info_registered(self):
        assert 'info' in TOOL_REGISTRY

    def test_all_12_tools_registered(self):
        expected = {'read', 'info', 'ls', 'tree', 'write', 'append',
                    'replace', 'insert_at_line', 'delete', 'copy',
                    'move', 'create_directory'}
        registered = set(TOOL_REGISTRY.keys())
        assert expected.issubset(registered)


class TestReadTool:
    def test_read_file(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("line1\nline2\nline3\n")
        # Import triggers registration
        from tools.filesystem import ReadTool
        tool = ReadTool()
        result = tool.call(json5.dumps({"path": str(test_file)}))
        # qwen-agent tools can return str, list, or dict
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert data["data"]["lines_returned"] == 3

    def test_read_file_not_found(self, tmp_path):
        from tools.filesystem import ReadTool
        tool = ReadTool()
        result = tool.call(json5.dumps({"path": str(tmp_path / "nope.txt")}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "error"
        assert "not found" in data["error"].lower()


class TestWriteTool:
    def test_write_creates_file(self, tmp_path):
        from tools.filesystem import WriteTool
        tool = WriteTool()
        target = str(tmp_path / "out.txt")
        result = tool.call(json5.dumps({"path": target, "content": "hello world"}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert os.path.isfile(target)
        assert open(target).read() == "hello world"


class TestLsTool:
    def test_ls_lists_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        from tools.filesystem import LsTool
        tool = LsTool()
        result = tool.call(json5.dumps({"path": str(tmp_path)}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert data["data"]["count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_filesystem.py -v`
Expected: FAIL — `ReadTool`, `WriteTool`, `LsTool` don't exist yet; TOOL_REGISTRY doesn't contain our tools.

- [ ] **Step 3: Convert all 12 filesystem tools**

Rewrite `tools/filesystem.py`. The pattern for each tool:

```python
"""Filesystem tools: read, write, and manage files and directories."""

import os
import json
import glob as glob_mod
import shutil
import json5
from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry
from config import DEFAULT_WORKSPACE


def _resolve(path: str) -> str:
    """Resolve path: expand ~, and place bare filenames into DEFAULT_WORKSPACE."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and os.sep not in path:
        os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)
        path = os.path.join(DEFAULT_WORKSPACE, path)
    return path


@register_tool('read')
class ReadTool(BaseTool):
    description = 'Read a file and return its contents with line numbers.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'start_line': {'type': 'integer', 'description': 'First line (0-indexed). Default: 0.', 'default': 0},
            'end_line': {'type': 'integer', 'description': 'Last line (exclusive). -1 = end.', 'default': -1},
        },
        'required': ['path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        start_line = p.get('start_line', 0)
        end_line = p.get('end_line', -1)
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))
        end = None if end_line == -1 else end_line
        subset = lines[start_line:end]
        numbered = [f'{i:>6}  {line.rstrip()}' for i, line in enumerate(subset, start=start_line + 1)]
        return tool_result(data={
            'path': os.path.abspath(path),
            'content': '\n'.join(numbered),
            'lines_returned': len(numbered),
        })


@register_tool('info')
class InfoTool(BaseTool):
    description = 'Return metadata about a file: size, modified time, type, line count.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
        },
        'required': ['path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))
        info_dict = {
            'path': os.path.abspath(path),
            'exists': True,
            'size_bytes': stat.st_size,
            'modified': stat.st_mtime,
            'is_file': os.path.isfile(path),
            'is_dir': os.path.isdir(path),
        }
        if info_dict['is_file']:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    info_dict['line_count'] = sum(1 for _ in f)
            except Exception:
                info_dict['line_count'] = None
        return tool_result(data=info_dict)


@register_tool('ls')
class LsTool(BaseTool):
    description = 'List directory contents, optionally recursive with glob pattern.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory to list.', 'default': '.'},
            'recursive': {'type': 'boolean', 'description': 'Walk subdirectories.', 'default': False},
            'pattern': {'type': 'string', 'description': "Glob pattern (e.g. '*.py').", 'default': '*'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p.get('path', '.'))
        recursive = p.get('recursive', False)
        pattern = p.get('pattern', '*')
        try:
            if recursive:
                entries = sorted(glob_mod.glob(os.path.join(path, '**', pattern), recursive=True))
            else:
                entries = sorted(glob_mod.glob(os.path.join(path, pattern)))
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'path': os.path.abspath(path), 'count': len(entries), 'entries': entries})


@register_tool('tree')
class TreeTool(BaseTool):
    description = 'Print the directory tree structure.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Root directory.', 'default': '.'},
            'max_depth': {'type': 'integer', 'description': 'Max depth (1-10).', 'default': 3},
            'show_hidden': {'type': 'boolean', 'description': 'Include dotfiles.', 'default': False},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p.get('path', '.'))
        max_depth = p.get('max_depth', 3)
        show_hidden = p.get('show_hidden', False)
        lines = []
        def _walk(dir_path, prefix, depth):
            if depth > max_depth:
                return
            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                lines.append(f'{prefix}[permission denied]')
                return
            if not show_hidden:
                entries = [e for e in entries if not e.startswith('.')]
            dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
            files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e))]
            for f in files:
                lines.append(f'{prefix}{f}')
            for d in dirs:
                lines.append(f'{prefix}{d}/')
                _walk(os.path.join(dir_path, d), prefix + '  ', depth + 1)
        lines.append(f'{os.path.basename(os.path.abspath(path))}/')
        _walk(path, '  ', 1)
        return tool_result(data={'path': os.path.abspath(path), 'tree': '\n'.join(lines)})


@register_tool('write')
class WriteTool(BaseTool):
    description = 'Write content to a file, creating parent directories if needed. WARNING: OVERWRITES entire file.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'content': {'type': 'string', 'description': 'Full file content to write.'},
        },
        'required': ['path', 'content'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        content = p['content']
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                written = f.write(content)
            return tool_result(data={'path': os.path.abspath(path), 'bytes_written': written})
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('append')
class AppendTool(BaseTool):
    description = 'Append content to the end of a file.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File path to append to.'},
            'content': {'type': 'string', 'description': 'Content to append.'},
        },
        'required': ['path', 'content'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        try:
            with open(path, 'a', encoding='utf-8') as f:
                written = f.write(p['content'])
            return tool_result(data={'path': os.path.abspath(path), 'bytes_appended': written})
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('replace')
class ReplaceTool(BaseTool):
    description = 'Replace exact string occurrences in a file.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File to edit.'},
            'old': {'type': 'string', 'description': 'Exact string to find.'},
            'new': {'type': 'string', 'description': 'Replacement string.'},
            'count': {'type': 'integer', 'description': 'Max replacements. 0 = all.', 'default': 1},
        },
        'required': ['path', 'old', 'new'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        old = p['old']
        new = p['new']
        count = p.get('count', 1)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return tool_result(error=str(e))
        if old not in content:
            return tool_result(error=f'String not found in {os.path.abspath(path)}')
        occurrences = content.count(old)
        if count == 0:
            new_content = content.replace(old, new)
            replaced = occurrences
        else:
            new_content = content.replace(old, new, count)
            replaced = min(count, occurrences)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'path': os.path.abspath(path), 'replacements': replaced})


@register_tool('insert_at_line')
class InsertAtLineTool(BaseTool):
    description = 'Insert content at a specific line number (1-indexed).'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File to edit.'},
            'line_number': {'type': 'integer', 'description': 'Line number to insert before (1-indexed).'},
            'content': {'type': 'string', 'description': 'Text to insert.'},
        },
        'required': ['path', 'line_number', 'content'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        line_number = p['line_number']
        content = p['content']
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            return tool_result(error=str(e))
        if not content.endswith('\n'):
            content += '\n'
        lines.insert(line_number - 1, content)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'path': os.path.abspath(path), 'inserted_at_line': line_number})


@register_tool('delete')
class DeleteTool(BaseTool):
    description = 'Delete a file, empty directory, or a range of lines from a file.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Path to delete or file to edit.'},
            'start': {'type': 'integer', 'description': 'First line to delete (1-indexed). 0 = delete file.', 'default': 0},
            'end': {'type': 'integer', 'description': 'Last line to delete (1-indexed, inclusive). 0 = delete file.', 'default': 0},
        },
        'required': ['path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        start = p.get('start', 0)
        end = p.get('end', 0)
        try:
            if start == 0 and end == 0:
                if os.path.isdir(path):
                    os.rmdir(path)
                    return tool_result(data={'path': os.path.abspath(path), 'action': 'deleted_directory'})
                else:
                    os.remove(path)
                    return tool_result(data={'path': os.path.abspath(path), 'action': 'deleted_file'})
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                removed_count = len(lines[start - 1:end])
                del lines[start - 1:end]
                with open(path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return tool_result(data={
                    'path': os.path.abspath(path), 'action': 'deleted_lines',
                    'start': start, 'end': end, 'lines_removed': removed_count,
                })
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('copy')
class CopyTool(BaseTool):
    description = 'Copy a file or directory.'
    parameters = {
        'type': 'object',
        'properties': {
            'src': {'type': 'string', 'description': 'Source path.'},
            'dst': {'type': 'string', 'description': 'Destination path.'},
        },
        'required': ['src', 'dst'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        src, dst = _resolve(p['src']), _resolve(p['dst'])
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
                shutil.copy2(src, dst)
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'src': os.path.abspath(src), 'dst': os.path.abspath(dst)})


@register_tool('move')
class MoveTool(BaseTool):
    description = 'Move or rename a file or directory.'
    parameters = {
        'type': 'object',
        'properties': {
            'src': {'type': 'string', 'description': 'Source path.'},
            'dst': {'type': 'string', 'description': 'Destination path.'},
        },
        'required': ['src', 'dst'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        src, dst = _resolve(p['src']), _resolve(p['dst'])
        try:
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            shutil.move(src, dst)
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'src': os.path.abspath(src), 'dst': os.path.abspath(dst)})


@register_tool('create_directory')
class CreateDirectoryTool(BaseTool):
    description = 'Create a directory and any missing parents.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory path to create.'},
        },
        'required': ['path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p['path'])
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            return tool_result(error=str(e))
        return tool_result(data={'path': os.path.abspath(path)})
```

Remove the `FILESYSTEM_TOOLS` list and `from langchain.tools import tool` import at the bottom.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_filesystem.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/filesystem.py tests/test_tools_filesystem.py
git commit -m "refactor: convert 12 filesystem tools from LangChain @tool to qwen-agent BaseTool"
```

---

## Task 4: Convert code search tools to qwen-agent BaseTool

**Files:**
- Modify: `tools/codesearch.py`
- Create: `tests/test_tools_codesearch.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_codesearch.py
"""Tests for qwen-agent code search tools."""

import json5
import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


class TestCodeSearchRegistration:
    def test_grep_registered(self):
        assert 'grep' in TOOL_REGISTRY

    def test_find_registered(self):
        assert 'find' in TOOL_REGISTRY

    def test_definition_registered(self):
        assert 'definition' in TOOL_REGISTRY


class TestGrepTool:
    def test_grep_finds_pattern(self, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        from tools.codesearch import GrepTool
        tool = GrepTool()
        result = tool.call(json5.dumps({"pattern": "hello", "path": str(tmp_path)}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert data["data"]["count"] == 1

    def test_grep_empty_pattern_error(self):
        from tools.codesearch import GrepTool
        tool = GrepTool()
        result = tool.call(json5.dumps({"pattern": ""}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "error"


class TestFindTool:
    def test_find_by_extension(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        from tools.codesearch import FindTool
        tool = FindTool()
        result = tool.call(json5.dumps({"path": str(tmp_path), "extension": ".py"}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert data["data"]["count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_codesearch.py -v`
Expected: FAIL — classes don't exist yet.

- [ ] **Step 3: Convert 3 code search tools**

Rewrite `tools/codesearch.py` using the same `@register_tool` + `BaseTool` pattern. Key changes:
- `grep` → `GrepTool` with `@register_tool('grep')`
- `find` → `FindTool` with `@register_tool('find')`
- `definition` → `DefinitionTool` with `@register_tool('definition')` — internally calls `GrepTool().call(...)` instead of `grep.invoke(...)`
- Remove `CODESEARCH_TOOLS` list
- Replace `from langchain.tools import tool` with `from qwen_agent.tools.base import BaseTool, register_tool`
- Add `import json5`

Each tool's `call` method: parse `params` with `json5.loads(params)`, run same logic, return `tool_result(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_codesearch.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/codesearch.py tests/test_tools_codesearch.py
git commit -m "refactor: convert 3 code search tools to qwen-agent BaseTool"
```

---

## Task 5: Convert web tools to qwen-agent BaseTool

**Files:**
- Modify: `tools/web.py`
- Create: `tests/test_tools_web.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_web.py
"""Tests for qwen-agent web tools."""

import json5
from qwen_agent.tools.base import TOOL_REGISTRY


class TestWebToolRegistration:
    def test_all_7_web_tools_registered(self):
        expected = {'web_search', 'fetch_url', 'webscrape', 'find_all',
                    'find_download_link', 'find_allowed_routes', 'browser_fetch'}
        registered = set(TOOL_REGISTRY.keys())
        assert expected.issubset(registered)


class TestFindAllTool:
    def test_finds_links(self):
        from tools.web import FindAllTool
        tool = FindAllTool()
        html = '<html><body><a href="x">Link1</a><a href="y">Link2</a></body></html>'
        result = tool.call(json5.dumps({"html": html, "target": "a"}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "success"
        assert data["data"]["count"] == 2

    def test_empty_html_error(self):
        from tools.web import FindAllTool
        tool = FindAllTool()
        result = tool.call(json5.dumps({"html": "", "target": "a"}))
        if isinstance(result, str):
            data = json5.loads(result)
        else:
            data = result
        assert data["status"] == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_web.py -v`
Expected: FAIL.

- [ ] **Step 3: Convert 7 web tools**

Rewrite `tools/web.py`: each `@tool` function → `@register_tool('name')` class. Keep the shared `_web_session`, `_apply_cookies()`, `_get_or_create_browser()` helpers unchanged. Remove `WEB_TOOLS` list.

Tools to convert:
- `web_search` → `WebSearchTool`
- `fetch_url` → `FetchUrlTool`
- `webscrape` → `WebscrapeTool`
- `find_all` → `FindAllTool`
- `find_download_link` → `FindDownloadLinkTool`
- `find_allowed_routes` → `FindAllowedRoutesTool`
- `browser_fetch` → `BrowserFetchTool`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_web.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/web.py tests/test_tools_web.py
git commit -m "refactor: convert 7 web tools to qwen-agent BaseTool"
```

---

## Task 6: Convert ecommerce tools to qwen-agent BaseTool

**Files:**
- Modify: `tools/ecommerce.py`
- Create: `tests/test_tools_ecommerce.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_ecommerce.py
"""Tests for qwen-agent ecommerce tools."""

from qwen_agent.tools.base import TOOL_REGISTRY


class TestEcommerceToolRegistration:
    def test_ebay_tools_registered(self):
        for name in ('ebay_search', 'ebay_sold_search', 'ebay_deep_scan'):
            assert name in TOOL_REGISTRY, f'{name} not registered'

    def test_flow_tools_registered(self):
        for name in ('cross_platform_search', 'deal_finder', 'enrichment_pipeline'):
            assert name in TOOL_REGISTRY, f'{name} not registered'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_ecommerce.py -v`
Expected: FAIL.

- [ ] **Step 3: Convert all ecommerce tools**

Same pattern as previous tasks. Keep helper functions (`_parse_ebay_listings`, etc.) as module-level functions. Convert each `@tool` function to a `@register_tool('name')` class. Remove `ECOMMERCE_TOOLS` and `FLOW_TOOLS` lists.

Also update any internal calls: if one ecommerce tool calls `webscrape.invoke(...)`, change to `from tools.web import WebscrapeTool; WebscrapeTool().call(json5.dumps({...}))`.

**IMPORTANT:** The ecommerce tools that use `ChatOllama` for analysis (like `ebay_deep_scan` or flow tools) — replace `ChatOllama` with qwen-agent LLM config. Use the same OpenAI-compatible endpoint pattern:

```python
from qwen_agent.llm import get_chat_model
_llm_cfg = {
    'model': 'qwen3:1.7b',
    'model_type': 'oai',
    'model_server': 'http://localhost:11434/v1',
    'api_key': 'EMPTY',
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_ecommerce.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/ecommerce.py tests/test_tools_ecommerce.py
git commit -m "refactor: convert ecommerce tools to qwen-agent BaseTool"
```

---

## Task 7: Convert onlyfans, torrent, mcp tools to qwen-agent BaseTool

**Files:**
- Modify: `tools/onlyfans.py`, `tools/torrent.py`, `tools/mcp.py`
- Create: `tests/test_tools_onlyfans.py`, `tests/test_tools_torrent.py`, `tests/test_tools_mcp.py`

- [ ] **Step 1: Write failing registration tests for all three modules**

```python
# tests/test_tools_onlyfans.py
from qwen_agent.tools.base import TOOL_REGISTRY

class TestOnlyFansRegistration:
    def test_tools_registered(self):
        expected = {'extract_media', 'extract_images_and_videos',
                    'scroll_conversations', 'scroll_messages',
                    'save_image', 'save_video'}
        assert expected.issubset(set(TOOL_REGISTRY.keys()))
```

```python
# tests/test_tools_torrent.py
from qwen_agent.tools.base import TOOL_REGISTRY

class TestTorrentRegistration:
    def test_tools_registered(self):
        expected = {'torrent_search', 'torrent_download', 'torrent_list_plugins',
                    'torrent_enable_plugin', 'torrent_add', 'torrent_list_active'}
        assert expected.issubset(set(TOOL_REGISTRY.keys()))
```

```python
# tests/test_tools_mcp.py
from qwen_agent.tools.base import TOOL_REGISTRY

class TestMcpRegistration:
    def test_connect_to_mcp_registered(self):
        assert 'connect_to_mcp' in TOOL_REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_onlyfans.py tests/test_tools_torrent.py tests/test_tools_mcp.py -v`
Expected: FAIL.

- [ ] **Step 3: Convert all three modules**

Same pattern. Replace `from langchain.tools import tool` with `from qwen_agent.tools.base import BaseTool, register_tool`. Add `import json5`. Convert each function. Remove tool list exports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_onlyfans.py tests/test_tools_torrent.py tests/test_tools_mcp.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/onlyfans.py tools/torrent.py tools/mcp.py tests/test_tools_onlyfans.py tests/test_tools_torrent.py tests/test_tools_mcp.py
git commit -m "refactor: convert onlyfans, torrent, mcp tools to qwen-agent BaseTool"
```

---

## Task 8: Convert accounting tools to qwen-agent BaseTool

**Files:**
- Modify: `tools/accounting.py`
- Create: `tests/test_tools_accounting.py`

- [ ] **Step 1: Write failing registration test**

```python
# tests/test_tools_accounting.py
from qwen_agent.tools.base import TOOL_REGISTRY

class TestAccountingRegistration:
    def test_all_21_tools_registered(self):
        expected = {
            'create_ledger', 'create_account', 'list_accounts',
            'get_account_balance', 'update_account',
            'journalize_transaction', 'search_journal',
            'void_transaction', 'account_ledger',
            'register_inventory_item', 'receive_inventory',
            'list_inventory_items', 'deactivate_inventory_item',
            'journalize_fifo_transaction', 'journalize_lifo_transaction',
            'inventory_valuation', 'close_period',
            'trial_balance', 'income_statement', 'balance_sheet',
            'cash_flow_statement',
        }
        registered = set(TOOL_REGISTRY.keys())
        assert expected.issubset(registered)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_accounting.py -v`
Expected: FAIL.

- [ ] **Step 3: Convert all 21 accounting tools**

Same pattern. Keep helpers (`_get_db`, `_get_ledger`, `_resolve_account`, `_parse_date`, `_parse_amount`, `DEFAULT_ACCOUNTS`, `_create_default_accounts`) as module-level functions. Convert each `@tool` function to `@register_tool('name')` class. Remove `ACCOUNTING_TOOLS` list.

Note: These tools use `flask_login.current_user` — this still works since the tool is called within a Flask request context. The `call` method will parse the params and use `current_user.id`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_accounting.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/accounting.py tests/test_tools_accounting.py
git commit -m "refactor: convert 21 accounting tools to qwen-agent BaseTool"
```

---

## Task 9: Update `tools/__init__.py` — import-only auto-registration

**Files:**
- Modify: `tools/__init__.py`

- [ ] **Step 1: Write the test**

```python
# Add to tests/test_tool_output.py or a new test:
def test_all_tools_registered_via_init():
    """Importing tools package registers all tools in qwen-agent."""
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools  # triggers all imports
    # Should have at least 60+ tools registered
    assert len(TOOL_REGISTRY) >= 60
```

- [ ] **Step 2: Rewrite `tools/__init__.py`**

```python
"""Tool registry — importing this module registers all tools with qwen-agent.

Each tools/*.py module uses @register_tool which auto-registers on import.
No manual list aggregation needed.
"""

import tools.filesystem
import tools.codesearch
import tools.web
import tools.ecommerce
import tools.onlyfans
import tools.torrent
import tools.mcp
import tools.accounting
```

- [ ] **Step 3: Run all tool tests**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tools_*.py tests/test_tool_output.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tools/__init__.py tests/
git commit -m "refactor: tools/__init__.py uses import-only auto-registration"
```

---

## Task 10: Add qwen-agent LLM config helper to `config.py`

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add LLM config builders**

Add to the bottom of `config.py`:

```python
def qwen_llm_cfg(model: str = "", num_ctx: int = 0) -> dict:
    """Build a qwen-agent LLM config pointing at the local Ollama instance.

    Args:
        model: Ollama model name. Defaults to env or 'qwen3:8b'.
        num_ctx: Context window size. Defaults to OLLAMA_NUM_CTX.

    Returns:
        Dict suitable for qwen-agent Assistant(llm=...).
    """
    return {
        'model': model or os.environ.get('CHAT_MODEL', 'qwen3:8b'),
        'model_type': 'oai',
        'model_server': os.environ.get('LLAMA_SERVER_URL', 'http://localhost:11434') + '/v1',
        'api_key': 'EMPTY',
        'generate_cfg': {
            'max_input_tokens': num_ctx or OLLAMA_NUM_CTX,
        },
    }


def qwen_curation_llm_cfg(model: str = "") -> dict:
    """Build a qwen-agent LLM config for 1.7B curation workers."""
    return {
        'model': model or TASK_EXTRACTOR_MODEL,
        'model_type': 'oai',
        'model_server': os.environ.get('LLAMA_SERVER_URL', 'http://localhost:11434') + '/v1',
        'api_key': 'EMPTY',
        'generate_cfg': {
            'max_input_tokens': OLLAMA_CURATION_NUM_CTX,
        },
    }
```

- [ ] **Step 2: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add config.py
git commit -m "feat: add qwen-agent LLM config builders to config.py"
```

---

## Task 11: Convert `context.py` to qwen-agent message format

qwen-agent uses plain dicts `{'role': 'user'|'assistant'|'system', 'content': '...'}` instead of LangChain message classes.

**Files:**
- Modify: `context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_context.py
"""Tests for context module with qwen-agent message format."""


class TestBuildHistory:
    def test_converts_user_message(self):
        from context import build_history
        rows = [{"role": "user", "content": "hello", "tool_calls": []}]
        result = build_history(rows)
        assert result == [{"role": "user", "content": "hello"}]

    def test_converts_assistant_message(self):
        from context import build_history
        rows = [{"role": "assistant", "content": "hi there", "tool_calls": []}]
        result = build_history(rows)
        assert result == [{"role": "assistant", "content": "hi there"}]

    def test_converts_tool_message_to_function_role(self):
        from context import build_history
        rows = [{"role": "tool", "content": "result data",
                 "tool_calls": [{"name": "read", "id": "1"}]}]
        result = build_history(rows)
        # qwen-agent uses 'function' role for tool results
        assert result[0]["role"] == "function"
        assert result[0]["name"] == "read"

    def test_truncates_tool_content(self):
        from context import build_history, TOOL_RESULT_MAX_CHARS
        long = "x" * (TOOL_RESULT_MAX_CHARS + 100)
        rows = [{"role": "tool", "content": long,
                 "tool_calls": [{"name": "read", "id": "1"}]}]
        result = build_history(rows)
        assert len(result[0]["content"]) == TOOL_RESULT_MAX_CHARS


class TestSerialize:
    def test_serialize_user(self):
        from context import serialize_user_message
        assert serialize_user_message("hi") == {"role": "user", "content": "hi", "tool_calls": []}

    def test_serialize_assistant(self):
        from context import serialize_assistant_message
        result = serialize_assistant_message("ok", tool_calls=[])
        assert result == {"role": "assistant", "content": "ok", "tool_calls": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_context.py -v`
Expected: FAIL — current `build_history` returns LangChain message objects.

- [ ] **Step 3: Rewrite `context.py`**

```python
"""Context pipeline: conversation history loading and serialization.

Converts DB rows to qwen-agent message dicts (role/content/name).
"""

TOOL_RESULT_MAX_CHARS = 4000


def _db_row_to_qwen(row: dict) -> dict:
    """Convert a DB message dict to a qwen-agent message dict.

    qwen-agent format:
    - user: {"role": "user", "content": "..."}
    - assistant: {"role": "assistant", "content": "..."}
    - tool result: {"role": "function", "name": "tool_name", "content": "..."}
    """
    role = row["role"]
    content = row.get("content", "")
    tool_calls = row.get("tool_calls", [])

    if role == "user":
        return {"role": "user", "content": content}

    if role == "assistant":
        return {"role": "assistant", "content": content}

    if role == "tool":
        truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
        tool_name = tool_calls[0]["name"] if tool_calls else "unknown"
        return {"role": "function", "name": tool_name, "content": truncated}

    return {"role": "user", "content": content}


def build_history(db_messages: list[dict]) -> list[dict]:
    """Convert DB message dicts to qwen-agent message dicts."""
    return [_db_row_to_qwen(row) for row in db_messages]


def serialize_user_message(content: str) -> dict:
    """Serialize a user message for DB storage."""
    return {"role": "user", "content": content, "tool_calls": []}


def serialize_assistant_message(content: str, tool_calls: list) -> dict:
    """Serialize an assistant message for DB storage."""
    return {"role": "assistant", "content": content, "tool_calls": tool_calls or []}


def serialize_tool_result(tool_name: str, tool_call_id: str, content: str) -> dict:
    """Serialize a tool result for DB storage."""
    truncated = content[:TOOL_RESULT_MAX_CHARS] if content else ""
    return {
        "role": "tool",
        "content": truncated,
        "tool_calls": [{"name": tool_name, "id": tool_call_id}],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_context.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add context.py tests/test_context.py
git commit -m "refactor: context.py uses qwen-agent message dicts instead of LangChain types"
```

---

## Task 12: Convert `task_extractor.py` to qwen-agent LLM

**Files:**
- Modify: `task_extractor.py`
- Create: `tests/test_task_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_task_extractor.py
"""Tests for task_extractor with qwen-agent LLM."""

from task_extractor import _parse_extractor_response, _build_extractor_prompt


class TestParseExtractorResponse:
    def test_valid_array(self):
        assert _parse_extractor_response('["task1", "task2"]') == ["task1", "task2"]

    def test_empty_array(self):
        assert _parse_extractor_response('[]') == []

    def test_strips_think_tags(self):
        raw = '<think>reasoning here</think>["task1"]'
        assert _parse_extractor_response(raw) == ["task1"]

    def test_malformed_returns_empty(self):
        assert _parse_extractor_response('not json') == []

    def test_non_string_items_filtered(self):
        assert _parse_extractor_response('[123, "real task", null]') == ["real task"]


class TestBuildExtractorPrompt:
    def test_builds_prompt_with_tasks_and_history(self):
        prompt = _build_extractor_prompt(
            "find prices",
            [{"title": "existing task", "status": "pending"}],
            [{"role": "user", "content": "hello"}],
        )
        assert "find prices" in prompt
        assert "existing task" in prompt
        assert "hello" in prompt

    def test_builds_prompt_no_history(self):
        prompt = _build_extractor_prompt("do stuff", [], [])
        assert "do stuff" in prompt
        assert "(none)" in prompt
```

- [ ] **Step 2: Run tests to verify parsing tests pass (they test pure functions)**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_task_extractor.py -v`
Expected: These should PASS since they test pure functions that don't change.

- [ ] **Step 3: Replace ChatOllama with qwen-agent LLM in `extract_tasks()`**

In `task_extractor.py`, replace:
```python
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from langchain.tools import tool
```

With:
```python
from qwen_agent.llm import get_chat_model
```

Replace the LLM invocation in `extract_tasks()`:
```python
    # Old:
    # llm = ChatOllama(model=...).bind_tools([cot_reasoning])
    # response = llm.invoke([HumanMessage(content=prompt)])
    # raw = response.content

    # New:
    from config import qwen_curation_llm_cfg
    llm = get_chat_model(qwen_curation_llm_cfg(TASK_EXTRACTOR_MODEL))
    messages = [
        {"role": "system", "content": _SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]
    # get_chat_model.chat() returns a generator of message dicts
    *_, final = llm.chat(messages=messages)
    raw = final[-1].get("content", "")
```

Remove the `cot_reasoning` tool definition — qwen-agent models handle reasoning natively with `enable_thinking`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_task_extractor.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add task_extractor.py tests/test_task_extractor.py
git commit -m "refactor: task_extractor uses qwen-agent LLM instead of ChatOllama"
```

---

## Task 13: Convert `tool_curator.py` to qwen-agent LLM

**Files:**
- Modify: `tool_curator.py`
- Create: `tests/test_tool_curator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tool_curator.py
"""Tests for tool_curator with qwen-agent LLM."""

from tool_curator import _parse_curator_response, _build_curator_prompt, CurationResult


class TestParseCuratorResponse:
    def test_pass_action(self):
        result = _parse_curator_response('{"action": "pass"}')
        assert result.action == "pass"
        assert result.groups == []

    def test_recommend_action(self):
        raw = '{"action": "recommend", "groups": ["Web Tools"], "reason": "need scraping"}'
        result = _parse_curator_response(raw)
        assert result.action == "recommend"
        assert result.groups == ["Web Tools"]
        assert result.reason == "need scraping"

    def test_invalid_group_name_filtered(self):
        raw = '{"action": "recommend", "groups": ["Nonexistent"], "reason": "test"}'
        result = _parse_curator_response(raw)
        assert result.action == "pass"  # no valid groups → pass

    def test_strips_think_tags(self):
        raw = '<think>hmm</think>{"action": "pass"}'
        result = _parse_curator_response(raw)
        assert result.action == "pass"

    def test_malformed_returns_pass(self):
        result = _parse_curator_response('garbage')
        assert result.action == "pass"


class TestBuildCuratorPrompt:
    def test_includes_tasks_and_groups(self):
        prompt = _build_curator_prompt(
            [{"title": "scrape data", "status": "pending"}],
            ["read", "write"],
        )
        assert "scrape data" in prompt
        assert "Filesystem" in prompt
```

- [ ] **Step 2: Run tests**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tool_curator.py -v`
Expected: Should PASS (testing pure functions).

- [ ] **Step 3: Replace ChatOllama with qwen-agent LLM in `curate_tools()`**

Same pattern as task_extractor. Replace:
```python
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
```

With:
```python
from qwen_agent.llm import get_chat_model
```

Replace the LLM invocation:
```python
    from config import qwen_curation_llm_cfg
    llm = get_chat_model(qwen_curation_llm_cfg(TOOL_CURATOR_MODEL))
    messages = [
        {"role": "system", "content": _SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]
    *_, final = llm.chat(messages=messages)
    raw = final[-1].get("content", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_tool_curator.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add tool_curator.py tests/test_tool_curator.py
git commit -m "refactor: tool_curator uses qwen-agent LLM instead of ChatOllama"
```

---

## Task 14: Refactor `main.py` — replace LangChain agent loop with qwen-agent Assistant

This is the most complex task. Replace the manual tool-call loop with `qwen-agent`'s `Assistant.run()`.

**Files:**
- Modify: `main.py`
- Modify: `workflow_groups.py` (update `tools_for_groups` to return tool objects)
- Modify: `routes/tools.py` (update tool metadata extraction)
- Create: `tests/test_main_chat.py`

- [ ] **Step 1: Write test for tool registry and metadata extraction**

```python
# tests/test_main_chat.py
"""Tests for the refactored chat pipeline."""

import json


def test_tool_registry_populated():
    """TOOL_REGISTRY should contain metadata for all registered tools."""
    # Import triggers registration
    import tools
    from main import TOOL_REGISTRY
    assert len(TOOL_REGISTRY) >= 60
    # Each entry should have name, description, params
    for entry in TOOL_REGISTRY:
        assert "name" in entry
        assert "description" in entry
        assert "params" in entry


def test_tool_meta_from_qwen():
    """_tool_meta should extract metadata from qwen-agent registered tools."""
    import tools
    from main import _tool_meta
    from qwen_agent.tools.base import TOOL_REGISTRY as QW_REG
    meta = _tool_meta(QW_REG['read'])
    assert meta["name"] == "read"
    assert "path" in meta["params"]
    assert meta["params"]["path"]["type"] == "string"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_main_chat.py -v`
Expected: FAIL — current `_tool_meta` expects LangChain tool objects.

- [ ] **Step 3: Rewrite `main.py` core sections**

### 3a. Replace imports at the top:

Remove:
```python
from langchain_ollama import ChatOllama
from langchain_core.messages import (HumanMessage, AIMessage, SystemMessage, ToolMessage)
from tools import ALL_TOOLS
```

Add:
```python
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY
import tools  # triggers registration
from config import qwen_llm_cfg
```

### 3b. Replace `_tool_meta()`:

```python
def _tool_meta(tool_cls) -> dict:
    """Extract name, description, and parameter info from a qwen-agent tool class."""
    props = {}
    schema = getattr(tool_cls, 'parameters', {})
    for pname, pinfo in schema.get('properties', {}).items():
        props[pname] = {
            'type': pinfo.get('type', 'string'),
            'description': pinfo.get('description', ''),
            'required': pname in schema.get('required', []),
        }
        if 'default' in pinfo:
            props[pname]['default'] = pinfo['default']
    name = tool_cls.name if hasattr(tool_cls, 'name') else ''
    desc = (tool_cls.description or '').split('\n')[0]
    return {'name': name, 'description': desc, 'params': props}

TOOL_REGISTRY = [_tool_meta(cls) for cls in QW_TOOL_REGISTRY.values()]
```

### 3c. Replace `_TOOL_BY_NAME` and `_get_llm()`:

Remove `_TOOL_BY_NAME`, `_get_llm()`, `_llm_cache`.

### 3d. Replace `parse_tool_calls()`:

Remove entirely. qwen-agent `Assistant.run()` handles tool call parsing internally.

### 3e. Replace the tool-calling loop inside `generate()`:

The key change: instead of manually calling `llm.stream()` → `parse_tool_calls()` → `tool_obj.invoke()` in a loop, create a qwen-agent `Assistant` with the user's tools and call `assistant.run()`.

However, we need streaming to frontend. qwen-agent's `Assistant.run()` yields incremental message lists. We process these and yield NDJSON chunks.

```python
def generate():
    nonlocal messages
    full_response = ""
    ordered_messages = []

    yield json.dumps({"conversation_id": conversation_id}) + "\n"

    # --- Recommendation flow (unchanged) ---
    # ... (keep existing recommendation logic) ...

    # Resolve final tool set
    final_tool_names = _initial_tool_names
    if accepted_groups:
        extra_tools = tools_for_groups(accepted_groups)
        final_tool_names = list(set(_initial_tool_names + extra_tools))

    # Build qwen-agent Assistant with user's tools
    function_list = [name for name in final_tool_names if name in QW_TOOL_REGISTRY]
    assistant = Assistant(
        llm=qwen_llm_cfg(model_name),
        function_list=function_list,
        system_message=SYSTEM_PROMPT,
    )

    # Build messages for qwen-agent
    qwen_messages = history + [{"role": "user", "content": augmented_msg}]

    try:
        prev_content = ""
        for responses in assistant.run(messages=qwen_messages):
            if not responses:
                continue
            last = responses[-1]
            role = last.get("role", "")
            content = last.get("content", "")

            if role == "assistant":
                # Stream new text tokens
                new_text = content[len(prev_content):]
                if new_text:
                    full_response = content
                    yield json.dumps({"chunk": new_text}) + "\n"
                prev_content = content

            elif role == "function":
                # Tool was called and returned
                fn_name = last.get("name", "")
                fn_content = last.get("content", "")
                yield json.dumps({
                    "tool_result": {
                        "tool": fn_name,
                        "output": fn_content[:500],
                    }
                }) + "\n"
                ordered_messages.append(("tool_result", {
                    "name": fn_name,
                    "tool_call_id": "",
                    "content": fn_content,
                }))

    except Exception as e:
        yield json.dumps({"error": str(e)}) + "\n"
        return

    # Persist to DB (same as before)
    # ...
```

**Note:** The exact streaming API of qwen-agent `Assistant.run()` needs to be verified. The `run()` method yields a list of message dicts that grows incrementally. The last element changes as the response progresses. When the assistant decides to call a tool, a `function_call` role appears; after execution, a `function` role with the result appears. When the assistant generates text, the `assistant` role content grows token by token.

### 3f. Update tool call streaming

qwen-agent handles tool calls internally. To stream `tool_call` events to the frontend, we need to detect when a new function_call appears in the response stream:

```python
    seen_fn_calls = 0
    for responses in assistant.run(messages=qwen_messages):
        # Check for new function_call entries
        fn_calls = [r for r in responses if r.get("role") == "function_call" or
                    (r.get("role") == "assistant" and r.get("function_call"))]
        if len(fn_calls) > seen_fn_calls:
            for fc in fn_calls[seen_fn_calls:]:
                call_info = fc.get("function_call", fc)
                yield json.dumps({
                    "tool_call": {
                        "tool": call_info.get("name", ""),
                        "input": call_info.get("arguments", ""),
                    }
                }) + "\n"
            seen_fn_calls = len(fn_calls)
        # ... rest of streaming logic
```

### 3g. Remove the self-correcting retry loop

qwen-agent handles multi-round tool calls natively. The self-correcting retry logic in the current code can be removed. If needed, tool-level retries are handled by the `@retry()` decorator on each tool's `call` method.

### 3h. Update `cli_chat()` function

Replace with qwen-agent Assistant:
```python
def cli_chat():
    model = cli_model_picker()
    if not model:
        print("No model selected.")
        return
    print(f"\nChatting with: {model}")
    print("Type 'quit' to exit\n")

    function_list = list(QW_TOOL_REGISTRY.keys())
    assistant = Assistant(
        llm=qwen_llm_cfg(model),
        function_list=function_list,
        system_message=SYSTEM_PROMPT,
    )
    history = []
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        history.append({"role": "user", "content": user_input})
        print("Agent: ", end="", flush=True)
        try:
            for responses in assistant.run(messages=history):
                pass
            if responses:
                last = responses[-1]
                if last.get("role") == "assistant":
                    print(last["content"])
                    history.append(last)
        except Exception as e:
            print(f"\n[Error: {e}]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/test_main_chat.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run all Python tests**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add main.py config.py routes/tools.py tests/test_main_chat.py
git commit -m "refactor: replace LangChain agent loop with qwen-agent Assistant.run()"
```

---

## Task 15: Update `workflow_groups.py` and `routes/tools.py` for qwen-agent registry

**Files:**
- Modify: `workflow_groups.py`
- Modify: `routes/tools.py`

- [ ] **Step 1: Update `routes/tools.py` to use qwen-agent TOOL_REGISTRY**

The `/api/tools` and `/api/workflows` endpoints need to extract metadata from qwen-agent tool classes instead of LangChain tool objects.

```python
# routes/tools.py — no changes needed if main.py's TOOL_REGISTRY is already updated
# But verify that /api/workflows still works correctly
```

- [ ] **Step 2: Run frontend tests to verify API compatibility**

Run: `cd /home/ermer/devproj/python/atomic_chat/frontend && npx vitest run`
Expected: All 95 frontend tests PASS. The frontend should not need changes since the API response shape (`name`, `description`, `params`) is preserved.

- [ ] **Step 3: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add workflow_groups.py routes/tools.py
git commit -m "refactor: update workflow_groups and routes for qwen-agent tool registry"
```

---

## Task 16: Clean up LangChain imports and verify full test suite

**Files:**
- Modify: `main.py` — remove any remaining LangChain imports
- Modify: `pyproject.toml` — keep `langchain` dep for now (MCP tools may still need it as a transitive dep)

- [ ] **Step 1: Grep for remaining LangChain imports**

Run: `cd /home/ermer/devproj/python/atomic_chat && grep -rn "from langchain" --include="*.py" | grep -v .venv | grep -v __pycache__`
Expected: Should show zero results in tool files, main.py, context.py, task_extractor.py, tool_curator.py. Only `client_agent.py` (separate WebSocket agent) may still have them.

- [ ] **Step 2: Remove any found LangChain imports from converted files**

If any remain in the converted files, remove them.

- [ ] **Step 3: Run full test suite**

Run: `cd /home/ermer/devproj/python/atomic_chat && uv run pytest tests/ -v && cd frontend && npx vitest run`
Expected: All Python and frontend tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add -A
git commit -m "chore: remove remaining LangChain imports from converted modules"
```

---

## Task 17: Update CLAUDE.md to reflect qwen-agent architecture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the relevant sections in CLAUDE.md**

Update the description to mention qwen-agent instead of LangChain. Update tool file descriptions to mention `BaseTool`/`@register_tool` pattern. Update the "Working on tools" section.

Key changes:
- Description: "Flask + qwen-agent + Ollama backend" (was "Flask + LangChain + Ollama")
- Tool pattern: "@register_tool + BaseTool classes" (was "@tool decorated functions")
- Agent loop: "qwen-agent Assistant.run()" (was "manual parse_tool_calls loop")

- [ ] **Step 2: Commit**

```bash
cd /home/ermer/devproj/python/atomic_chat
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for qwen-agent architecture"
```

---

## Summary of changes

| # | Task | Files | Tools converted |
|---|------|-------|-----------------|
| 1 | Add dependency | pyproject.toml | — |
| 2 | Update _output.py | tools/_output.py | — |
| 3 | Filesystem tools | tools/filesystem.py | 12 |
| 4 | Code search tools | tools/codesearch.py | 3 |
| 5 | Web tools | tools/web.py | 7 |
| 6 | Ecommerce tools | tools/ecommerce.py | ~9 |
| 7 | OF/Torrent/MCP tools | 3 files | ~13 |
| 8 | Accounting tools | tools/accounting.py | 21 |
| 9 | tools/__init__.py | tools/__init__.py | — |
| 10 | Config LLM helper | config.py | — |
| 11 | Context module | context.py | — |
| 12 | Task extractor | task_extractor.py | — |
| 13 | Tool curator | tool_curator.py | — |
| 14 | Main chat loop | main.py | — |
| 15 | Workflows + routes | 2 files | — |
| 16 | Cleanup | all files | — |
| 17 | Docs | CLAUDE.md | — |

**Total tools converted:** ~65
**LangChain dependencies removed from:** tools/, main.py, context.py, task_extractor.py, tool_curator.py
