"""Filesystem tools: read, write, and manage files and directories."""

import os
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


# ── Read Operations ──────────────────────────────────────────────────────────

@register_tool('read')
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


@register_tool('tree')
class TreeTool(BaseTool):
    description = 'Print the directory tree structure.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Root directory. Defaults to current directory.'},
            'max_depth': {'type': 'integer', 'description': 'Maximum depth to traverse. Range: 1-10.'},
            'show_hidden': {'type': 'boolean', 'description': 'Include dotfiles/dotdirs. Default: false.'},
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

        def _walk(dir_path: str, prefix: str, depth: int):
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


# ── Write Operations ─────────────────────────────────────────────────────────

@register_tool('write')
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
        content = p['content']

        try:
            with open(path, 'a', encoding='utf-8') as f:
                written = f.write(content)
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


@register_tool('move')
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
