"""Tests for codesearch tools (qwen-agent BaseTool pattern)."""
import json
import os
import tempfile

import pytest
from qwen_agent.tools.base import TOOL_REGISTRY


# ── Registration tests ────────────────────────────────────────────────────────

def test_all_3_tools_registered():
    """Import triggers @register_tool; all 3 names must appear in the registry."""
    # Import individual classes (which loads the module and registers tools)
    # without going through tools/__init__.py (which would re-register other tools).
    from tools.codesearch import GrepTool, FindTool, DefinitionTool  # noqa: F401
    expected = {'grep', 'find', 'definition'}
    for name in expected:
        assert name in TOOL_REGISTRY, f"Tool '{name}' not found in TOOL_REGISTRY"


def test_class_names_importable():
    """Each class must be importable by name from tools.codesearch."""
    from tools.codesearch import GrepTool, FindTool, DefinitionTool
    assert GrepTool is not None
    assert FindTool is not None
    assert DefinitionTool is not None


def test_no_codesearch_tools_list():
    """CODESEARCH_TOOLS list should no longer exist."""
    import importlib
    cs = importlib.import_module('tools.codesearch')
    assert not hasattr(cs, 'CODESEARCH_TOOLS'), \
        'CODESEARCH_TOOLS list should have been removed'


def test_no_langchain_import():
    """langchain should not be imported in codesearch module."""
    import importlib
    import inspect
    cs = importlib.import_module('tools.codesearch')
    src = inspect.getsource(cs)
    assert 'from langchain' not in src, 'langchain import found in codesearch.py'


# ── GrepTool ──────────────────────────────────────────────────────────────────

def test_grep_returns_dict():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'test.py')
        with open(path, 'w') as f:
            f.write('def hello():\n    return "world"\n')
        result = tool.call(json.dumps({'pattern': 'hello', 'path': d}))
        assert isinstance(result, dict)
        assert result['status'] == 'success'
        assert result['data']['count'] >= 1
        assert any('hello' in m['snippet'] for m in result['data']['matches'])


def test_grep_no_match_returns_empty():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'test.py')
        with open(path, 'w') as f:
            f.write('def hello():\n    pass\n')
        result = tool.call(json.dumps({'pattern': 'zzznomatch', 'path': d}))
        assert result['status'] == 'success'
        assert result['data']['count'] == 0
        assert result['data']['matches'] == []


def test_grep_invalid_regex_returns_error():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        result = tool.call(json.dumps({'pattern': '[invalid(', 'path': d}))
        assert result['status'] == 'error'
        assert 'Invalid regex' in result['error']


def test_grep_empty_pattern_returns_error():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    result = tool.call(json.dumps({'pattern': '   '}))
    assert result['status'] == 'error'
    assert 'pattern' in result['error']


def test_grep_file_pattern_filters():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        py_file = os.path.join(d, 'code.py')
        txt_file = os.path.join(d, 'notes.txt')
        with open(py_file, 'w') as f:
            f.write('hello python\n')
        with open(txt_file, 'w') as f:
            f.write('hello text\n')
        result = tool.call(json.dumps({'pattern': 'hello', 'path': d, 'file_pattern': '*.py'}))
        assert result['status'] == 'success'
        files = [m['file'] for m in result['data']['matches']]
        assert any('code.py' in fp for fp in files)
        assert all('notes.txt' not in fp for fp in files)


def test_grep_ignore_case():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'test.py')
        with open(path, 'w') as f:
            f.write('HELLO world\n')
        result = tool.call(json.dumps({'pattern': 'hello', 'path': d, 'ignore_case': True}))
        assert result['status'] == 'success'
        assert result['data']['count'] == 1


def test_grep_context_lines():
    from tools.codesearch import GrepTool
    tool = GrepTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'test.py')
        with open(path, 'w') as f:
            f.write('line1\nline2\ntarget\nline4\nline5\n')
        result = tool.call(json.dumps({'pattern': 'target', 'path': d, 'context': 1}))
        assert result['status'] == 'success'
        snippet = result['data']['matches'][0]['snippet']
        assert 'line2' in snippet
        assert 'line4' in snippet


# ── FindTool ──────────────────────────────────────────────────────────────────

def test_find_returns_dict():
    from tools.codesearch import FindTool
    tool = FindTool()
    with tempfile.TemporaryDirectory() as d:
        for name in ['a.py', 'b.py', 'c.txt']:
            open(os.path.join(d, name), 'w').close()
        result = tool.call(json.dumps({'path': d, 'name': '*.py'}))
        assert isinstance(result, dict)
        assert result['status'] == 'success'
        files = result['data']['files']
        assert any('a.py' in fp for fp in files)
        assert any('b.py' in fp for fp in files)
        assert all('c.txt' not in fp for fp in files)


def test_find_by_extension():
    from tools.codesearch import FindTool
    tool = FindTool()
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'script.py'), 'w').close()
        open(os.path.join(d, 'readme.md'), 'w').close()
        result = tool.call(json.dumps({'path': d, 'extension': 'py'}))
        assert result['status'] == 'success'
        files = result['data']['files']
        assert any('script.py' in fp for fp in files)
        assert all('readme.md' not in fp for fp in files)


def test_find_by_contains():
    from tools.codesearch import FindTool
    tool = FindTool()
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, 'match.py'), 'w') as f:
            f.write('import os\n')
        with open(os.path.join(d, 'no_match.py'), 'w') as f:
            f.write('x = 1\n')
        result = tool.call(json.dumps({'path': d, 'contains': 'import os'}))
        assert result['status'] == 'success'
        files = result['data']['files']
        assert any('match.py' in fp for fp in files)
        assert all('no_match.py' not in fp for fp in files)


def test_find_max_results():
    from tools.codesearch import FindTool
    tool = FindTool()
    with tempfile.TemporaryDirectory() as d:
        for i in range(10):
            open(os.path.join(d, f'file{i}.py'), 'w').close()
        result = tool.call(json.dumps({'path': d, 'max_results': 3}))
        assert result['status'] == 'success'
        assert len(result['data']['files']) <= 3


# ── DefinitionTool ────────────────────────────────────────────────────────────

def test_definition_finds_function():
    from tools.codesearch import DefinitionTool
    tool = DefinitionTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'module.py')
        with open(path, 'w') as f:
            f.write('def my_func():\n    pass\n\nclass MyClass:\n    pass\n')
        result = tool.call(json.dumps({'symbol': 'my_func', 'path': d}))
        assert isinstance(result, dict)
        assert result['status'] == 'success'
        assert any('my_func' in m['snippet'] for m in result['data']['matches'])


def test_definition_finds_class():
    from tools.codesearch import DefinitionTool
    tool = DefinitionTool()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'module.py')
        with open(path, 'w') as f:
            f.write('class MyService:\n    pass\n')
        result = tool.call(json.dumps({'symbol': 'MyService', 'path': d}))
        assert result['status'] == 'success'
        assert result['data']['count'] >= 1


def test_definition_empty_symbol_returns_error():
    from tools.codesearch import DefinitionTool
    tool = DefinitionTool()
    result = tool.call(json.dumps({'symbol': ''}))
    assert result['status'] == 'error'
    assert 'symbol' in result['error']


def test_definition_uses_grep_tool_internally():
    """DefinitionTool.call() must delegate to GrepTool, not grep.invoke."""
    from tools.codesearch import DefinitionTool, GrepTool
    called = []
    original_call = GrepTool.call

    def patched_call(self, params, **kwargs):
        called.append(params)
        return original_call(self, params, **kwargs)

    GrepTool.call = patched_call
    try:
        tool = DefinitionTool()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'x.py')
            with open(path, 'w') as f:
                f.write('def foo():\n    pass\n')
            tool.call(json.dumps({'symbol': 'foo', 'path': d}))
        assert len(called) >= 1, 'GrepTool.call was not invoked by DefinitionTool'
    finally:
        GrepTool.call = original_call
