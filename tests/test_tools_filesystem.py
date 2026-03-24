"""Tests for filesystem tools (qwen-agent BaseTool pattern)."""
import json
import os
import tempfile

import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration tests ────────────────────────────────────────────────────────

def test_all_12_tools_registered():
    """Import triggers @register_tool; all 12 names must appear in the registry."""
    import tools.filesystem  # noqa: F401 — side-effect: registers tools
    expected = {
        'read', 'info', 'ls', 'tree',
        'write', 'append', 'replace', 'insert_at_line',
        'delete', 'copy', 'move', 'create_directory',
    }
    for name in expected:
        assert name in TOOL_REGISTRY, f"Tool '{name}' not found in TOOL_REGISTRY"


def test_class_names_importable():
    """Each class must be importable by name from tools.filesystem."""
    from tools.filesystem import (
        ReadTool, InfoTool, LsTool, TreeTool,
        WriteTool, AppendTool, ReplaceTool, InsertAtLineTool,
        DeleteTool, CopyTool, MoveTool, CreateDirectoryTool,
    )
    assert ReadTool is not None
    assert CreateDirectoryTool is not None


def test_no_filesystem_tools_list():
    """FILESYSTEM_TOOLS list should no longer exist."""
    import tools.filesystem as fs
    assert not hasattr(fs, 'FILESYSTEM_TOOLS'), \
        "FILESYSTEM_TOOLS list should have been removed"


# ── ReadTool ──────────────────────────────────────────────────────────────────

def test_read_returns_dict_with_content():
    from tools.filesystem import ReadTool
    tool = ReadTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('line1\nline2\nline3\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path}))
        assert isinstance(result, dict)
        assert result['status'] == 'success'
        assert 'line1' in result['data']['content']
        assert 'line2' in result['data']['content']
        assert result['data']['lines_returned'] == 3
    finally:
        os.unlink(path)


def test_read_with_line_range():
    from tools.filesystem import ReadTool
    tool = ReadTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('line1\nline2\nline3\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'start_line': 1, 'end_line': 2}))
        assert result['status'] == 'success'
        assert 'line2' in result['data']['content']
        assert 'line1' not in result['data']['content']
        assert result['data']['lines_returned'] == 1
    finally:
        os.unlink(path)


def test_read_missing_file_returns_error():
    from tools.filesystem import ReadTool
    tool = ReadTool()
    result = tool.call(json.dumps({'path': '/nonexistent/path/file.txt'}))
    assert result['status'] == 'error'
    assert 'not found' in result['error'].lower()


# ── InfoTool ──────────────────────────────────────────────────────────────────

def test_info_returns_metadata():
    from tools.filesystem import InfoTool
    tool = InfoTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('hello\nworld\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path}))
        assert result['status'] == 'success'
        d = result['data']
        assert d['exists'] is True
        assert d['is_file'] is True
        assert d['is_dir'] is False
        assert d['size_bytes'] > 0
        assert d['line_count'] == 2
    finally:
        os.unlink(path)


def test_info_missing_file_returns_error():
    from tools.filesystem import InfoTool
    tool = InfoTool()
    result = tool.call(json.dumps({'path': '/nonexistent/file.txt'}))
    assert result['status'] == 'error'


# ── LsTool ────────────────────────────────────────────────────────────────────

def test_ls_lists_directory():
    from tools.filesystem import LsTool
    tool = LsTool()
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'a.txt'), 'w').close()
        open(os.path.join(d, 'b.py'), 'w').close()
        result = tool.call(json.dumps({'path': d}))
        assert result['status'] == 'success'
        assert result['data']['count'] == 2
        entries = result['data']['entries']
        assert any('a.txt' in e for e in entries)
        assert any('b.py' in e for e in entries)


def test_ls_with_pattern():
    from tools.filesystem import LsTool
    tool = LsTool()
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'a.txt'), 'w').close()
        open(os.path.join(d, 'b.py'), 'w').close()
        result = tool.call(json.dumps({'path': d, 'pattern': '*.py'}))
        assert result['status'] == 'success'
        assert result['data']['count'] == 1
        assert any('b.py' in e for e in result['data']['entries'])


# ── TreeTool ──────────────────────────────────────────────────────────────────

def test_tree_returns_tree_string():
    from tools.filesystem import TreeTool
    tool = TreeTool()
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'subdir'))
        open(os.path.join(d, 'file.txt'), 'w').close()
        result = tool.call(json.dumps({'path': d}))
        assert result['status'] == 'success'
        tree_str = result['data']['tree']
        assert 'file.txt' in tree_str
        assert 'subdir/' in tree_str


# ── WriteTool ─────────────────────────────────────────────────────────────────

def test_write_creates_file():
    from tools.filesystem import WriteTool
    tool = WriteTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'out.txt')
        result = tool.call(json.dumps({'path': path, 'content': 'hello world'}))
        assert result['status'] == 'success'
        assert result['data']['bytes_written'] == len('hello world')
        with open(path) as f:
            assert f.read() == 'hello world'


def test_write_overwrites_existing():
    from tools.filesystem import WriteTool
    tool = WriteTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('old content')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'content': 'new content'}))
        assert result['status'] == 'success'
        with open(path) as f:
            assert f.read() == 'new content'
    finally:
        os.unlink(path)


def test_write_creates_parent_dirs():
    from tools.filesystem import WriteTool
    tool = WriteTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'a', 'b', 'c.txt')
        result = tool.call(json.dumps({'path': path, 'content': 'deep'}))
        assert result['status'] == 'success'
        assert os.path.exists(path)


# ── AppendTool ────────────────────────────────────────────────────────────────

def test_append_adds_content():
    from tools.filesystem import AppendTool
    tool = AppendTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('first\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'content': 'second\n'}))
        assert result['status'] == 'success'
        assert result['data']['bytes_appended'] == len('second\n')
        with open(path) as f:
            assert f.read() == 'first\nsecond\n'
    finally:
        os.unlink(path)


# ── ReplaceTool ───────────────────────────────────────────────────────────────

def test_replace_substitutes_text():
    from tools.filesystem import ReplaceTool
    tool = ReplaceTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('foo bar foo')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'old': 'foo', 'new': 'baz'}))
        assert result['status'] == 'success'
        assert result['data']['replacements'] == 1
        with open(path) as f:
            assert f.read() == 'baz bar foo'
    finally:
        os.unlink(path)


def test_replace_all_occurrences():
    from tools.filesystem import ReplaceTool
    tool = ReplaceTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('foo bar foo')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'old': 'foo', 'new': 'baz', 'count': 0}))
        assert result['status'] == 'success'
        assert result['data']['replacements'] == 2
        with open(path) as f:
            assert f.read() == 'baz bar baz'
    finally:
        os.unlink(path)


def test_replace_missing_string_returns_error():
    from tools.filesystem import ReplaceTool
    tool = ReplaceTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('hello world')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'old': 'nothere', 'new': 'x'}))
        assert result['status'] == 'error'
        assert 'not found' in result['error'].lower()
    finally:
        os.unlink(path)


# ── InsertAtLineTool ──────────────────────────────────────────────────────────

def test_insert_at_line():
    from tools.filesystem import InsertAtLineTool
    tool = InsertAtLineTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('line1\nline3\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'line_number': 2, 'content': 'line2'}))
        assert result['status'] == 'success'
        assert result['data']['inserted_at_line'] == 2
        with open(path) as f:
            lines = f.readlines()
        assert lines[1].strip() == 'line2'
        assert lines[2].strip() == 'line3'
    finally:
        os.unlink(path)


# ── DeleteTool ────────────────────────────────────────────────────────────────

def test_delete_file():
    from tools.filesystem import DeleteTool
    tool = DeleteTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        path = f.name
    result = tool.call(json.dumps({'path': path}))
    assert result['status'] == 'success'
    assert result['data']['action'] == 'deleted_file'
    assert not os.path.exists(path)


def test_delete_empty_directory():
    from tools.filesystem import DeleteTool
    tool = DeleteTool()
    with tempfile.TemporaryDirectory() as parent:
        d = os.path.join(parent, 'empty')
        os.makedirs(d)
        result = tool.call(json.dumps({'path': d}))
        assert result['status'] == 'success'
        assert result['data']['action'] == 'deleted_directory'
        assert not os.path.exists(d)


def test_delete_lines():
    from tools.filesystem import DeleteTool
    tool = DeleteTool()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('line1\nline2\nline3\n')
        path = f.name
    try:
        result = tool.call(json.dumps({'path': path, 'start': 2, 'end': 2}))
        assert result['status'] == 'success'
        assert result['data']['action'] == 'deleted_lines'
        assert result['data']['lines_removed'] == 1
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert lines[0].strip() == 'line1'
        assert lines[1].strip() == 'line3'
    finally:
        os.unlink(path)


# ── CopyTool ──────────────────────────────────────────────────────────────────

def test_copy_file():
    from tools.filesystem import CopyTool
    tool = CopyTool()
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'src.txt')
        dst = os.path.join(d, 'dst.txt')
        with open(src, 'w') as f:
            f.write('content')
        result = tool.call(json.dumps({'src': src, 'dst': dst}))
        assert result['status'] == 'success'
        assert os.path.exists(src)
        assert os.path.exists(dst)
        with open(dst) as f:
            assert f.read() == 'content'


# ── MoveTool ──────────────────────────────────────────────────────────────────

def test_move_file():
    from tools.filesystem import MoveTool
    tool = MoveTool()
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'src.txt')
        dst = os.path.join(d, 'dst.txt')
        with open(src, 'w') as f:
            f.write('content')
        result = tool.call(json.dumps({'src': src, 'dst': dst}))
        assert result['status'] == 'success'
        assert not os.path.exists(src)
        assert os.path.exists(dst)


# ── CreateDirectoryTool ───────────────────────────────────────────────────────

def test_create_directory():
    from tools.filesystem import CreateDirectoryTool
    tool = CreateDirectoryTool()
    with tempfile.TemporaryDirectory() as d:
        new_dir = os.path.join(d, 'a', 'b', 'c')
        result = tool.call(json.dumps({'path': new_dir}))
        assert result['status'] == 'success'
        assert os.path.isdir(new_dir)


def test_create_directory_idempotent():
    from tools.filesystem import CreateDirectoryTool
    tool = CreateDirectoryTool()
    with tempfile.TemporaryDirectory() as d:
        result1 = tool.call(json.dumps({'path': d}))
        result2 = tool.call(json.dumps({'path': d}))
        assert result1['status'] == 'success'
        assert result2['status'] == 'success'
