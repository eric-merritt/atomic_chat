"""Filesystem tools: read, write, and manage files and directories."""

import os
import glob as glob_mod
import shutil
import re
from subprocess import run

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result, retry
from tools._enrich import enrichable
from config import DEFAULT_WORKSPACE


def _resolve(path: str) -> str:
    """Resolve path: expand ~, and place bare filenames into DEFAULT_WORKSPACE."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and os.sep not in path:
        os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)
        path = os.path.join(DEFAULT_WORKSPACE, path)
    return path


# ── Read Operations ──────────────────────────────────────────────────────────

@register_tool('fs_read')
@enrichable
class ReadTool(BaseTool):
    description = 'Read a file and return its contents with line numbers.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'start_line': {'type': 'integer', 'description': 'First line to include (0-indexed). Default: 0.'},
            'end_line': {'type': 'integer', 'description': 'Last line to include (exclusive). -1 = read to end.'},
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


@register_tool('fs_info')
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


@register_tool('fs_ls')
class LsTool(BaseTool):
    description = 'List directory contents, optionally recursive with glob pattern.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory to list. Defaults to current directory.'},
            'recursive': {'type': 'boolean', 'description': 'If true, walk subdirectories.'},
            'pattern': {'type': 'string', 'description': "Glob pattern to filter results (e.g. '*.py')."},
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


@register_tool('fs_tree')
@enrichable
class TreeTool(BaseTool):
    description = 'Print a directory tree with configurable depth using lsd.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory path to tree. Default: current directory.'},
            'max_depth': {'type': 'integer', 'description': 'Max recursion depth. Default: 3.'},
            'show_hidden': {'type': 'boolean', 'description': 'Include hidden files/dirs. Default: false.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p.get('path', '.'))
        max_depth = p.get('max_depth', 3)
        show_hidden = p.get('show_hidden', False)

        args = ['lsd', '--tree', '--depth', str(max_depth)]
        if show_hidden:
            args.append('-a')
        args.append(path)

        try:
            result = run(args, capture_output=True, text=True)
        except FileNotFoundError:
            return tool_result(error='lsd not found in PATH')

        if result.returncode != 0:
            return tool_result(error=result.stderr.strip() or f'lsd exited with code {result.returncode}')

        return tool_result(data={'path': os.path.abspath(path), 'tree': result.stdout.rstrip()})


# ── Write Operations ─────────────────────────────────────────────────────────

@register_tool('fs_write')
class WriteTool(BaseTool):
    description = 'Write content to a file, creating parent directories if needed. DESTRUCTIVE: overwrites existing content.'
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


@register_tool('fs_append')
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
        content = p['content']

        try:
            with open(path, 'a', encoding='utf-8') as f:
                written = f.write(content)
            return tool_result(data={'path': os.path.abspath(path), 'bytes_appended': written})
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('fs_replace')
class ReplaceTool(BaseTool):
    description = 'Replace exact string occurrences in a file.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File to edit.'},
            'old': {'type': 'string', 'description': 'Exact string to find. Must exist in the file.'},
            'new': {'type': 'string', 'description': 'Replacement string.'},
            'count': {'type': 'integer', 'description': 'Max replacements. 0 = replace all occurrences.'},
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


@register_tool('fs_insert_at_line')
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


@register_tool('fs_delete')
class DeleteTool(BaseTool):
    description = (
        'Delete a file, empty directory, or a range of lines from a file. '
        'If start and end are both 0, deletes the file/directory. '
        'Otherwise, deletes lines start-end (1-indexed, inclusive).'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Path to delete or file to edit.'},
            'start': {'type': 'integer', 'description': 'First line to delete (1-indexed). 0 = delete the file itself.'},
            'end': {'type': 'integer', 'description': 'Last line to delete (1-indexed, inclusive). 0 = delete the file itself.'},
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
                    'path': os.path.abspath(path),
                    'action': 'deleted_lines',
                    'start': start,
                    'end': end,
                    'lines_removed': removed_count,
                })
        except Exception as e:
            return tool_result(error=str(e))


# ── File Management ──────────────────────────────────────────────────────────

@register_tool('fs_copy')
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
        src = _resolve(p['src'])
        dst = _resolve(p['dst'])

        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
                shutil.copy2(src, dst)
        except Exception as e:
            return tool_result(error=str(e))

        return tool_result(data={'src': os.path.abspath(src), 'dst': os.path.abspath(dst)})


@register_tool('fs_move')
class MoveTool(BaseTool):
    description = 'Move or rename a file or directory. WARNING: overwrites destination if it exists.'
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
        src = _resolve(p['src'])
        dst = _resolve(p['dst'])
        
        # Check if source exists
        if not os.path.exists(src):
            return tool_result(error=f"Source path {src} does not exist.")
        
        # Check if destination already exists (either file or directory)
        if os.path.exists(dst):
            return tool_result(error=f"Destination path {dst} already exists. Overwriting is not allowed.")
        
        # Check if source is a file or directory, and handle accordingly
        try:
            # Check if source is a file or directory and move it
            if os.path.isfile(src):
                # If the source is a file, move it to the destination
                os.rename(src, dst)
            elif os.path.isdir(src):
                # If the source is a directory, use shutil.move (to handle directories)
                import shutil
                shutil.move(src, dst)
            else:
                return tool_result(error="Source is neither a file nor a directory.")

            # Return the result with absolute paths
            return tool_result(data={'src': os.path.abspath(src), 'dst': os.path.abspath(dst)})

        except Exception as e:
            return tool_result(error=f"Failed to move {src} to {dst}: {e}")

@register_tool('fs_ls_dir')
@enrichable
class ListDirectoriesTool(BaseTool):
    _FLAGS = {
        'all':       ('-a',               'Include hidden entries (dotfiles).'),
        'long':      ('-l',               'Include extended metadata: permissions, owner, size, modified time.'),
        'recursive': ('-R',               'Recurse into subdirectories.'),
        'dirs_only': ('--directory-only', 'Show directories only.'),
        'timesort':  ('-t',               'Sort by modification time (newest first).'),
        'sizesort':  ('-S',               'Sort by file size (largest first).'),
        'extsort':   ('-X',               'Sort by file extension.'),
        'reverse':   ('-r',               'Reverse the sort order.'),
    }
    description = 'List directory contents using lsd, returned as structured JSON with optional metadata.'
    parameters = {
        'type': 'object',
        'properties': {
            'path':  {'type': 'string',  'description': 'Directory to list. Defaults to home directory.'},
            'depth': {'type': 'integer', 'description': 'Max recursion depth (only with recursive=true).'},
            **{k: {'type': 'boolean', 'description': desc} for k, (_, desc) in _FLAGS.items()},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = _resolve(p.get('path', os.getenv('HOME', '.')))

        args = ['lsd', '--output-format', 'json']
        args += [self._FLAGS[key][0] for key in self._FLAGS.keys() if p.get(key)]
        if p.get('depth') is not None:
            args.extend(['--depth', str(p['depth'])])
        args.append(path)

        try:
            result = run(args, capture_output=True, text=True)
        except FileNotFoundError:
            return tool_result(error='lsd not found in PATH')

        if result.returncode != 0:
            return tool_result(error=result.stderr.strip() or f'lsd exited with code {result.returncode}')

        try:
            entries = json5.loads(result.stdout)
        except Exception as e:
            return tool_result(error=f'Failed to parse lsd output: {e}')

        return tool_result(data={'path': os.path.abspath(path), 'entries': entries})














@register_tool('fs_make_dir')
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

@register_tool('fs_grep')
@enrichable
class GrepTool(BaseTool):
    description = 'Search file contents with regex using ripgrep, returning matches with context.'
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
        import json as _json
        p = json5.loads(params)
        pattern = p.get('pattern', '')
        path = p.get('path', '.')
        file_pattern = p.get('file_pattern', '')
        ignore_case = p.get('ignore_case', False)
        context_lines = p.get('context', 0)
        max_results = p.get('max_results', 50)

        if not pattern or not pattern.strip():
            return tool_result(error='pattern must be a non-empty string')

        args = ['rg', '--json']
        if ignore_case:
            args.append('-i')
        if context_lines:
            args.extend(['-C', str(context_lines)])
        if file_pattern:
            args.extend(['-g', file_pattern])
        args.extend(['--', pattern, os.path.expanduser(path)])

        try:
            result = run(args, capture_output=True, text=True)
        except FileNotFoundError:
            return tool_result(error='rg (ripgrep) not found in PATH')

        if result.returncode == 2:
            return tool_result(error=result.stderr.strip())

        # Parse NDJSON into a flat list of (file, lineno, type, text)
        flat: list[tuple[str, int, str, str]] = []
        current_file = None
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                obj = _json.loads(line)
            except Exception:
                continue
            t = obj.get('type')
            data = obj.get('data', {})
            if t == 'begin':
                current_file = data.get('path', {}).get('text', '')
            elif t in ('match', 'context') and current_file is not None:
                flat.append((
                    current_file,
                    data.get('line_number', 0),
                    t,
                    data.get('lines', {}).get('text', '').rstrip(),
                ))

        # Build per-match records with context snippets
        matches = []
        for file, lineno, t, _ in flat:
            if t != 'match':
                continue
            if len(matches) >= max_results:
                break
            seen: set[int] = set()
            snippet_entries: list[tuple[int, str]] = []
            for f2, ln2, t2, text2 in flat:
                if f2 != file or abs(ln2 - lineno) > context_lines:
                    continue
                if ln2 in seen:
                    continue
                seen.add(ln2)
                marker = '>' if t2 == 'match' and ln2 == lineno else ' '
                snippet_entries.append((ln2, f'  {marker} {ln2:>5}  {text2}'))
            snippet_entries.sort(key=lambda x: x[0])
            matches.append({
                'file': file,
                'line': lineno,
                'snippet': '\n'.join(s for _, s in snippet_entries),
            })

        return tool_result(data={
            'pattern': pattern,
            'count': len(matches),
            'truncated': len(matches) >= max_results,
            'matches': matches,
        })


@register_tool('fs_find')
@enrichable
class FindTool(BaseTool):
    description = 'Find files by name pattern, extension, or content using fd.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory to search. Defaults to current directory.'},
            'name': {'type': 'string', 'description': 'Glob pattern for filename (e.g. "test_*", "*.py").'},
            'extension': {'type': 'string', 'description': 'File extension filter (e.g. ".py", "py").'},
            'contains': {'type': 'string', 'description': 'Only return files containing this exact string.'},
            'max_results': {'type': 'integer', 'description': 'Maximum files to return. Range: 1-500.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        path = os.path.expanduser(p.get('path', '.'))
        name = p.get('name', '')
        extension = p.get('extension', '')
        contains = p.get('contains', '')
        max_results = p.get('max_results', 50)

        args = ['fdfind', '--type', 'f']
        if not contains:
            args.extend(['--max-results', str(max_results)])
        if extension:
            args.extend(['-e', extension.lstrip('.')])
        if name:
            args.extend(['--glob', name])
        args.append(path)

        try:
            result = run(args, capture_output=True, text=True)
        except FileNotFoundError:
            return tool_result(error='fdfind not found in PATH')

        if result.returncode != 0:
            return tool_result(error=result.stderr.strip())

        files = [f for f in result.stdout.splitlines() if f]

        if contains and files:
            rg_result = run(
                ['rg', '--files-with-matches', '--fixed-strings', '--', contains] + files,
                capture_output=True, text=True,
            )
            files = [f for f in rg_result.stdout.splitlines() if f]

        files = files[:max_results]
        return tool_result(data={
            'path': path,
            'count': len(files),
            'files': files,
        })


@register_tool('fs_find_def')
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
