"""Code search tools: grep, find, definition."""

import os
import re
import glob as glob_mod

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result, retry


# ── Search Operations ────────────────────────────────────────────────────────

@register_tool('cs_grep')
class GrepTool(BaseTool):
    description = 'Search file contents with regex, returning matches with context.'
    parameters = {
        'type': 'object',
        'properties': {
            'pattern': {'type': 'string', 'description': 'Regex pattern to search for. Must be non-empty.'},
            'path': {'type': 'string', 'description': 'File or directory to search in. Defaults to current directory.'},
            'file_pattern': {'type': 'string', 'description': "Glob to filter which files to search (e.g. '*.py')."},
            'ignore_case': {'type': 'boolean', 'description': 'Case-insensitive matching.'},
            'context': {'type': 'integer', 'description': 'Number of lines before/after each match to include.'},
            'max_results': {'type': 'integer', 'description': 'Maximum number of matches to return. Range: 1-500.'},
        },
        'required': ['pattern'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        pattern = p.get('pattern', '')
        path = p.get('path', '.')
        file_pattern = p.get('file_pattern', '*')
        ignore_case = p.get('ignore_case', False)
        context = p.get('context', 0)
        max_results = p.get('max_results', 50)

        if not pattern or not pattern.strip():
            return tool_result(error='pattern must be a non-empty string')

        path = os.path.expanduser(path)
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return tool_result(error=f'Invalid regex pattern: {e}')

        results = []

        if os.path.isfile(path):
            files = [path]
        else:
            files = sorted(glob_mod.glob(os.path.join(path, '**', file_pattern), recursive=True))

        for filepath in files:
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
            except (PermissionError, OSError):
                continue
            for i, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, i - context)
                    end = min(len(lines), i + context + 1)
                    snippet = []
                    for j in range(start, end):
                        marker = '>' if j == i else ' '
                        snippet.append(f'  {marker} {j + 1:>5}  {lines[j].rstrip()}')
                    results.append({
                        'file': filepath,
                        'line': i + 1,
                        'snippet': '\n'.join(snippet),
                    })
                    if len(results) >= max_results:
                        return tool_result(data={
                            'pattern': pattern,
                            'count': len(results),
                            'truncated': True,
                            'matches': results,
                        })

        if not results:
            return tool_result(data={'pattern': pattern, 'count': 0, 'matches': []})

        return tool_result(data={
            'pattern': pattern,
            'count': len(results),
            'truncated': False,
            'matches': results,
        })


@register_tool('cs_find')
class FindTool(BaseTool):
    description = 'Find files by name pattern, extension, or content.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory to search. Defaults to current directory.'},
            'name': {'type': 'string', 'description': 'Glob pattern for filename (e.g. "test_*", "*.py"). If empty, matches all files.'},
            'extension': {'type': 'string', 'description': 'File extension filter (e.g. ".py", "py"). Do not combine with name.'},
            'contains': {'type': 'string', 'description': 'Only return files containing this exact string.'},
            'max_results': {'type': 'integer', 'description': 'Maximum files to return. Range: 1-500.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = p.get('path', '.')
        name = p.get('name', '')
        extension = p.get('extension', '')
        contains = p.get('contains', '')
        max_results = p.get('max_results', 50)

        path = os.path.expanduser(path)
        pat = name if name else '*'
        if extension:
            if not extension.startswith('.'):
                extension = '.' + extension
            pat = f'*{extension}' if not name else pat

        matches = sorted(glob_mod.glob(os.path.join(path, '**', pat), recursive=True))
        matches = [m for m in matches if os.path.isfile(m)]

        if extension and name:
            matches = [m for m in matches if m.endswith(extension)]

        if contains:
            filtered = []
            for m in matches:
                try:
                    with open(m, 'r', encoding='utf-8', errors='replace') as f:
                        if contains in f.read():
                            filtered.append(m)
                except (PermissionError, OSError):
                    continue
            matches = filtered

        files = matches[:max_results]
        return tool_result(data={
            'path': path,
            'count': len(files),
            'files': files,
        })


@register_tool('cs_def')
class DefinitionTool(BaseTool):
    description = 'Find where a function, class, or variable is defined.'
    parameters = {
        'type': 'object',
        'properties': {
            'symbol': {'type': 'string', 'description': 'Name of the symbol to find. Must be non-empty.'},
            'path': {'type': 'string', 'description': 'Directory to search. Defaults to current directory.'},
            'file_pattern': {'type': 'string', 'description': 'Glob pattern for files to search (e.g. "*.py", "*.js").'},
        },
        'required': ['symbol'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        import json
        p = json5.loads(params)
        symbol = p.get('symbol', '')
        path = p.get('path', '.')
        file_pattern = p.get('file_pattern', '*.py')

        if not symbol or not symbol.strip():
            return tool_result(error='symbol must be a non-empty string')

        patterns = [
            rf'^\s*(def|class)\s+{re.escape(symbol)}\b',
            rf'^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b',
            rf'^{re.escape(symbol)}\s*=',
        ]
        combined = '|'.join(f'({p})' for p in patterns)
        return GrepTool().call(json.dumps({
            'pattern': combined,
            'path': path,
            'file_pattern': file_pattern,
            'context': 3,
        }))
