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
from tools._access import check_fs_access
from config import DEFAULT_WORKSPACE


def _resolve(path: str) -> str:
    """Resolve path: expand ~, and place bare filenames into DEFAULT_WORKSPACE."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and os.sep not in path:
        os.makedirs(DEFAULT_WORKSPACE, exist_ok=True)
        path = os.path.join(DEFAULT_WORKSPACE, path)
    return path


# ============================================================================
# Read Operations
# ============================================================================

_READ_PAGE = 200


def _page_for(line_start: int) -> dict:
    """Return page number (1-indexed) and the start_line arg to pass to fs_read."""
    page = (line_start - 1) // _READ_PAGE + 1
    return {'page': page, 'read_start_line': (page - 1) * _READ_PAGE}


@register_tool('fs_read')
@enrichable
class ReadTool(BaseTool):
    description = (
        'Read a file and return its contents with line numbers. '
        'Returns at most 200 lines per call. When has_more is true, '
        'call again with start_line=next_start_line to read the next page.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'start_line': {'type': 'integer', 'description': 'First line to include (0-indexed). Default: 0.'},
            'end_line': {'type': 'integer', 'description': 'Last line to include (exclusive). Capped at start_line+200.'},
        },
        'required': ['path'],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
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

        total = len(lines)
        cap = start_line + _READ_PAGE
        if end_line == -1 or end_line > cap:
            end_line = cap
        subset = lines[start_line:end_line]
        numbered = [f'{i:>6}  {line.rstrip()}' for i, line in enumerate(subset, start=start_line + 1)]
        has_more = end_line < total
        result = {
            'path': os.path.abspath(path),
            'content': '\n'.join(numbered),
            'lines_returned': len(numbered),
            'total_lines': total,
            'has_more': has_more,
        }
        if has_more:
            result['next_start_line'] = end_line
        return tool_result(data=result)


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

    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        p = json5.loads(params)
        path = _resolve(p['path'])

        try:
            stat = os.stat(path)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            import time
            return tool_result(data={
                'path': os.path.abspath(path),
                'size': stat.st_size,
                'modified_time': time.ctime(stat.st_mtime),
                'type': 'file' if os.path.isfile(path) else 'directory',
                'line_count': len(lines),
            })
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))


@register_tool('fs_summary')
class SummaryTool(BaseTool):
    """Provide a lightweight structural summary of a file without full contents.

    Best practices for the summary:
    - Include line numbers for all definitions (essential for navigation)
    - Map file structure (classes, functions, imports)
    - Describe component purposes briefly
    - Keep token usage minimal while maintaining utility
    - Enable precise navigation without "flying blind"

    This tool combines fs_info and fs_find_def to provide:
    - File metadata (size, line count, modified time)
    - Structural overview with line number mapping
    - Component descriptions
    - Navigation guidance
    """
    description = 'Provide a structural summary of a file with line numbers for definitions, metadata, and navigation guidance without full contents.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
        },
        'required': ['path'],
    }

    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        import time
        p = json5.loads(params)
        path = _resolve(p['path'])

        # Get file metadata first
        try:
            stat = os.stat(path)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))

        # Extract structural information with line numbers
        structure = []

        # Find imports
        import_pattern = r'^import\s+(.+)$|^from\s+(.+?)\s+import\s+(.+)$'
        for i, line in enumerate(lines):
            match = re.match(import_pattern, line.strip())
            if match:
                structure.append({
                    'type': 'import',
                    'line': i + 1,
                    'content': line.strip(),
                    'purpose': 'Module import'
                })

        # Find class definitions
        class_pattern = r'^class\s+(\w+)'
        for i, line in enumerate(lines):
            match = re.match(class_pattern, line.strip())
            if match:
                class_name = match.group(1)
                # Try to find docstring or description
                purpose = 'Class definition'
                for j in range(i, min(i + 10, len(lines))):
                    if lines[j].strip().startswith('"""') or lines[j].strip().startswith("'''"):
                        # Extract docstring content
                        docstring = lines[j].strip()
                        if 'description' in docstring.lower() or 'purpose' in docstring.lower():
                            purpose = docstring
                            break
                structure.append({
                    'type': 'class',
                    'name': class_name,
                    'line': i + 1,
                    'purpose': purpose
                })

        # Find function definitions
        func_pattern = r'^(def|async\s+def)\s+(\w+)'
        for i, line in enumerate(lines):
            match = re.match(func_pattern, line.strip())
            if match:
                func_name = match.group(2)
                func_type = 'async' if match.group(1) == 'async def' else 'sync'
                # Try to find docstring or description
                purpose = 'Function definition'
                for j in range(i, min(i + 10, len(lines))):
                    if lines[j].strip().startswith('"""') or lines[j].strip().startswith("'''"):
                        docstring = lines[j].strip()
                        if 'description' in docstring.lower() or 'purpose' in docstring.lower():
                            purpose = docstring
                            break
                structure.append({
                    'type': 'function',
                    'name': func_name,
                    'line': i + 1,
                    'func_type': func_type,
                    'purpose': purpose
                })

        # Find key structural elements (decorators, register_tool calls)
        decorator_pattern = r'^@\w+'
        for i, line in enumerate(lines):
            match = re.match(decorator_pattern, line.strip())
            if match:
                structure.append({
                    'type': 'decorator',
                    'line': i + 1,
                    'content': line.strip(),
                    'purpose': 'Function decorator'
                })

        return tool_result(data={
            'path': os.path.abspath(path),
            'metadata': {
                'size': stat.st_size,
                'modified_time': time.ctime(stat.st_mtime),
                'type': 'file' if os.path.isfile(path) else 'directory',
                'line_count': len(lines),
            },
            'structure': structure,
            'summary': f'File contains {len([s for s in structure if s["type"] == "class"])} classes, {len([s for s in structure if s["type"] == "function"])} functions, and {len([s for s in structure if s["type"] == "import"])} imports. Use fs_read with line ranges to view specific sections, or fs_find_def to locate definitions.'
        })


# ============================================================================
# Write Operations
# ============================================================================

@register_tool('fs_write')
@enrichable
class WriteTool(BaseTool):
    """Write content to a file in manageable chunks to avoid token overflow.

    Constraints:
    - Files are written in chunks of manageable tokens (max ~4096 tokens per chunk)
    - Large content is automatically split into multiple write operations
    - Each chunk is written sequentially to ensure data integrity
    - Supports both append and overwrite modes
    - DEFAULTS TO APPEND MODE
    """
    description = 'Write content to a file in chunks to manage token limits safely.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'content': {'type': 'string', 'description': 'Content to write to the file.'},
            'mode': {'type': 'string', 'description': 'Write mode: "append" (default) or "overwrite".', 'enum': ['append', 'overwrite']},
            'chunk_size': {'type': 'integer', 'description': 'Maximum tokens per chunk. Default: 4096.'},
        },
        'required': ['path', 'content'],
    }

    def _split_into_chunks(self, content: str, max_tokens: int = 4096) -> list[str]:
        """Split content into chunks of manageable token size."""
        # Rough estimate: 1 token ≈ 4 characters
        max_chars = max_tokens * 4
        chunks = []
        for i in range(0, len(content), max_chars):
            chunks.append(content[i:i + max_chars])
        return chunks

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        import time
        p = json5.loads(params)
        path = _resolve(p['path'])
        content = p['content']
        mode = p.get('mode', 'append')  # DEFAULT TO APPEND
        chunk_size = p.get('chunk_size', 4096)

        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path) or DEFAULT_WORKSPACE, exist_ok=True)

            # Split content into chunks
            chunks = self._split_into_chunks(content, chunk_size)

            # Write all chunks sequentially
            if mode == 'overwrite':
                with open(path, 'w', encoding='utf-8') as f:
                    for chunk in chunks:
                        f.write(chunk)
            else:  # append (default)
                with open(path, 'a', encoding='utf-8') as f:
                    for chunk in chunks:
                        f.write(chunk)

            stat = os.stat(path)
            return tool_result(data={
                'path': os.path.abspath(path),
                'status': 'success',
                'chunks_written': len(chunks),
                'total_size': stat.st_size,
                'mode': mode,
            })
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))


# ============================================================================
# Search Operations
# ============================================================================

@register_tool('fs_grep')
class GrepTool(BaseTool):
    """Search for patterns in files using ripgrep (rg) via subprocess.
    
    This tool uses the system 'rg' command to perform fast, efficient text searching.
    Supports regex patterns, case sensitivity options, and multiple file searching.
    
    Requirements:
    - ripgrep (rg) must be installed on the system
    - Works on files and directories
    """
    description = 'Search for patterns in files using ripgrep (rg) command-line tool.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File or directory path to search.'},
            'pattern': {'type': 'string', 'description': 'Text or regex pattern to search for.'},
            'case_sensitive': {'type': 'boolean', 'description': 'Enable case-sensitive search. Default: false.'},
            'max_results': {'type': 'integer', 'description': 'Maximum number of results to return. Default: 50.'},
        },
        'required': ['path', 'pattern'],
    }
    
    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        p = json5.loads(params)
        path = _resolve(p['path'])
        pattern = p['pattern']
        case_sensitive = p.get('case_sensitive', False)
        max_results = p.get('max_results', 50)
        
        try:
            # Build rg command arguments
            cmd = ['rg', pattern]
            
            # Add case sensitivity flag if requested
            if case_sensitive:
                cmd.append('--no-ignore-case')
            else:
                cmd.append('-i')  # Case-insensitive by default
            
            # Limit output
            cmd.append(f'-l')  # List files only (we'll read them separately)
            
            # Run the command
            result = run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return tool_result(error=f'Ripgrep error: {result.stderr.strip()}')
            
            # Get list of matching files
            matching_files = result.stdout.strip().split('\n')
            matching_files = [f for f in matching_files if f.strip()][:max_results]
            
            # Now search with line numbers and context
            cmd = ['rg', pattern]
            if case_sensitive:
                cmd.append('--no-ignore-case')
            else:
                cmd.append('-i')
            cmd.append('-n')  # Show line numbers
            cmd.append(f'-C2')  # Show 2 lines context
            
            if os.path.isfile(path):
                cmd.append(path)
            else:
                cmd.append(path)
                cmd.append('--glob')
                cmd.append('*.py')
            
            result = run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return tool_result(error=f'Ripgrep search error: {result.stderr.strip()}')
            
            return tool_result(data={
                'path': os.path.abspath(path),
                'pattern': pattern,
                'case_sensitive': case_sensitive,
                'results': result.stdout.strip(),
                'matching_files': matching_files,
                'result_count': len(matching_files),
            })
        
        except FileNotFoundError:
            return tool_result(error='ripgrep (rg) command not found. Please install ripgrep.')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except TimeoutError:
            return tool_result(error='Search timed out after 30 seconds.')
        except Exception as e:
            return tool_result(error=f'Search error: {str(e)}')


# ============================================================================
# Definition Finder Tool
# ============================================================================

@register_tool('fs_find_def')
class FindDefinitionTool(BaseTool):
    """Find function and class definitions by name and return their line numbers."""
    description = 'Find function and class definitions by name and return their line numbers in the code.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'name': {'type': 'string', 'description': 'Name of the function or class to find.'},
            'def_type': {'type': 'string', 'description': 'Type of definition: "function", "class", or "any". Default: "any".', 'enum': ['function', 'class', 'any']},
        },
        'required': ['path', 'name'],
    }

    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        p = json5.loads(params)
        path = _resolve(p['path'])
        name = p['name']
        def_type = p.get('def_type', 'any')

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))

        results = []

        # Search patterns based on def_type
        if def_type == 'any' or def_type == 'function':
            # Find function definitions
            func_pattern = rf'^(def|async\s+def)\s+{re.escape(name)}\s*\('
            for i, line in enumerate(lines):
                match = re.match(func_pattern, line.strip())
                if match:
                    func_type = 'async' if match.group(1) == 'async def' else 'sync'
                    # Find the extent of the function (until next def or end of file)
                    start_line = i + 1
                    end_line = self._find_definition_end(lines, i)
                    results.append({
                        'type': 'function',
                        'name': name,
                        'line_start': start_line,
                        'line_end': end_line,
                        'func_type': func_type,
                        'content_preview': line.strip(),
                        **_page_for(start_line),
                    })

        if def_type == 'any' or def_type == 'class':
            # Find class definitions
            class_pattern = rf'^class\s+{re.escape(name)}'
            for i, line in enumerate(lines):
                match = re.match(class_pattern, line.strip())
                if match:
                    start_line = i + 1
                    end_line = self._find_definition_end(lines, i)
                    results.append({
                        'type': 'class',
                        'name': name,
                        'line_start': start_line,
                        'line_end': end_line,
                        'content_preview': line.strip(),
                        **_page_for(start_line),
                    })

        if not results:
            return tool_result(error=f'No definition found for "{name}" in {os.path.abspath(path)}')

        return tool_result(data={
            'path': os.path.abspath(path),
            'searched_name': name,
            'definitions_found': len(results),
            'results': results,
            'guidance': 'Each result includes page and read_start_line. Call fs_read(path, start_line=read_start_line) to load that page, then use line_start/line_end to locate the definition within it.'
        })

    def _find_definition_end(self, lines: list[str], start_idx: int) -> int:
        """Find the end line of a definition by detecting indentation changes or next definition."""
        # Get the indentation level of the definition line
        def_line = lines[start_idx]
        base_indent = len(def_line) - len(def_line.lstrip())

        end_idx = start_idx
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if not stripped:  # Empty line
                continue
            current_indent = len(line) - len(line.lstrip())
            # If we find a line with same or less indentation that's not empty, we've reached the end
            if current_indent <= base_indent and stripped:
                # Check if it's a new definition
                if re.match(r'^(def|async\s+def|class)\s+\w+', stripped):
                    end_idx = i
                    break
                else:
                    end_idx = i
                    break
            else:
                end_idx = i

        return end_idx + 1  # Convert to 1-indexed line number


# ============================================================================
# Line Replacement Tool
# ============================================================================

@register_tool('fs_replace')
class ReplaceTool(BaseTool):
    """Replace specific lines in a file with new content.

    This tool allows targeted modifications to specific line ranges in a file.
    It reads the file, replaces the specified lines, and writes back the modified content.

    Best practices:
    - Use fs_find_def to locate definitions before making edits
    - Use fs_read to view the specific sections to modify
    - Never read or rewrite entire files blindly
    - Make targeted, surgical changes
    - Always verify the changes are correct before committing
    """
    description = 'Replace specific lines in a file with new content.'
    parameters = {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute or relative file path.'},
            'start_line': {'type': 'integer', 'description': 'First line to replace (1-indexed, inclusive).'},
            'end_line': {'type': 'integer', 'description': 'Last line to replace (1-indexed, inclusive). -1 = to end of file.'},
            'replacement': {'type': 'string', 'description': 'Content to replace the specified lines with.'},
        },
        'required': ['path', 'start_line', 'end_line', 'replacement'],
    }

    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        p = json5.loads(params)
        path = _resolve(p['path'])
        start_line = p['start_line']
        end_line = p['end_line']
        replacement = p['replacement']

        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
        except FileNotFoundError:
            return tool_result(error=f'File not found: {os.path.abspath(path)}')
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))

        n = len(lines)
        # Convert 1-indexed inclusive to 0-indexed slice bounds
        start_idx = start_line - 1
        end_idx = n if end_line == -1 else end_line  # end_line is inclusive, slice end is exclusive

        if start_idx < 0 or start_idx >= n:
            return tool_result(error=f'Invalid start_line: {start_line}. File has {n} lines.')
        if end_idx < start_line or end_idx > n:
            return tool_result(error=f'Invalid end_line: {end_line}. Must be >= start_line ({start_line}) and <= {n}.')

        lines_to_replace = lines[start_idx:end_idx]
        new_lines = [replacement if replacement.endswith('\n') else replacement + '\n']
        modified_lines = lines[:start_idx] + new_lines + lines[end_idx:]

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)

            stat = os.stat(path)
            return tool_result(data={
                'path': os.path.abspath(path),
                'status': 'success',
                'lines_replaced': len(lines_to_replace),
                'start_line': start_line,
                'end_line': end_line if end_line != -1 else n,
                'new_size': stat.st_size,
                'guidance': 'Changes applied. Verify the modifications are correct and test the code.'
            })
        except PermissionError:
            return tool_result(error=f'Permission denied: {os.path.abspath(path)}')
        except Exception as e:
            return tool_result(error=str(e))

@register_tool('fs_tree')
class FilesystemTreeTool(BaseTool):
    """Print the directory structure with its files and subdirectories"""

    description = "This tool lists all the files and subdirectories within the given directory, allowing for easier and more general traversal. Use it to find files that may differ slightly from the names the user provides."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "an absolute or relative DIRECTORY path."
            },
        },
        "required": ["path"]
    }
    
    def call(self, params: str, **kwargs):
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        try:
            p = json5.loads(params)
            path = _resolve(p['path'])
            results = os.listdir(path)
            return results
        except NotADirectoryError:
            print("Target must be a directory")
        
