# Agentic Chat — LangChain + Ollama

An agentic chat application that pairs local Ollama models with 20 filesystem, search, and web tools via LangChain's tool-calling agent. Includes both an interactive CLI and a Flask REST API.

All tools are **always bound** to the agent regardless of selection state. The tool browser (with `>` / `<` controls) is for inspecting what parameters each tool requires from the user.

## Setup

```bash
# install dependencies (requires uv)
uv sync

# make sure ollama is running
ollama serve
```

## Running

### Interactive CLI

```bash
uv run python main.py
```

You'll see the main menu:

```
=== Agentic Chat (LangChain + Ollama) ===

  1. Pick model
  2. Browse tools
  3. Chat
  4. Set system prompt
  5. Start API server
  q. Quit
```

### Flask API server

```bash
# default port 5000
uv run python main.py --serve

# custom port
uv run python main.py --serve --port=8080
```

## CLI Usage Examples

### 1. Pick a model

```
> 1

Available Ollama models:
   0. qwen2.5-coder:14b
   1. qwen2.5:14b
   2. llama3.2-better-prompts:latest

Select model number: 0
Model set to: qwen2.5-coder:14b
```

### 2. Browse tools

```
> 2

=====================================================================================
AVAILABLE                               | >  | SELECTED
-------------------------------------------------------------------------------------
   0. read_file                          |    |
   1. file_info                          |    |
   2. list_dir                           |    |
   3. tree                               |    |
   4. write_file                         |    |
   5. append_file                        |    |
   ...                                   |    |
-------------------------------------------------------------------------------------
Commands:  > N  (select)   < N  (deselect)   ? N  (inspect)   q  (done)
```

Select a tool with `>` to see its required params:

```
> > 0

  + read_file: Read a file and return its contents with line numbers.
    Params required from user:
      *path (string): Absolute or relative file path.
      start_line (integer)(default: 0): First line to include (0-indexed).
      end_line (integer)(default: -1): Last line to include (exclusive). -1 = read to end.
```

Inspect any tool with `?`:

```
> ? 13

  grep: Search file contents with regex, returning matches with context.
    *pattern (string): Regex pattern to search for.
    path (string)(default: .): File or directory to search in.
    file_pattern (string)(default: *): Glob to filter which files to search (e.g. '*.py').
    ignore_case (boolean)(default: False): Case-insensitive matching.
    context (integer)(default: 0): Number of lines before/after each match to include.
    max_results (integer)(default: 50): Maximum number of matches to return.
```

Deselect with `<`:

```
> < 0
```

### 3. Chat

```
> 3

Chat with qwen2.5-coder:14b (20 tools bound)
Type 'quit' to exit, 'clear' to reset history.

You: list all python files in the current directory
Agent: Here are the Python files in the current directory:
  ./main.py
  ./tools.py

You: show me the first 10 lines of tools.py
Agent:      1  """
     2  Agent tools derived from ~/agent_tooling.py.
     3  Each function is wrapped with LangChain's @tool decorator...
     ...

You: search for "ebay" in all .py files
Agent: Found matches in tools.py:
  tools.py:510
  >   510  EBAY_SORT_OPTIONS = {
  ...

You: clear
  (history cleared)

You: quit
```

## Flask API Examples

Start the server first:

```bash
uv run python main.py --serve
```

### List available models

```bash
curl http://localhost:5000/api/models
```

```json
{"models": ["qwen2.5-coder:14b", "qwen2.5:14b", "llama3.2-better-prompts:latest"], "current": null}
```

### Select a model

```bash
curl -X POST http://localhost:5000/api/models \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2.5-coder:14b"}'
```

### Browse tools (2-column state)

```bash
curl http://localhost:5000/api/tools
```

```json
{
  "available": [
    {"index": 0, "name": "read_file", "description": "Read a file and return its contents with line numbers.", "params": {"path": {"type": "string", "required": true}, "start_line": {"type": "integer", "required": false, "default": 0}}},
    ...
  ],
  "selected": []
}
```

### Select a tool (> button)

```bash
curl -X POST http://localhost:5000/api/tools/select \
  -d '{"index": 0}'
```

### Deselect a tool (< button)

```bash
curl -X POST http://localhost:5000/api/tools/deselect \
  -d '{"index": 0}'
```

### Inspect a tool's params

```bash
curl http://localhost:5000/api/tools/13
```

```json
{
  "name": "grep",
  "description": "Search file contents with regex, returning matches with context.",
  "params": {
    "pattern": {"type": "string", "description": "Regex pattern to search for.", "required": true},
    "path": {"type": "string", "description": "File or directory to search in.", "required": false, "default": "."},
    "file_pattern": {"type": "string", "description": "Glob to filter which files to search.", "required": false, "default": "*"},
    "ignore_case": {"type": "boolean", "required": false, "default": false},
    "context": {"type": "integer", "required": false, "default": 0},
    "max_results": {"type": "integer", "required": false, "default": 50}
  }
}
```

### Chat (synchronous)

```bash
curl -X POST http://localhost:5000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "list all files in the current directory"}'
```

```json
{"response": "Here are the files in the current directory:\n  main.py\n  tools.py\n  pyproject.toml\n  README.md"}
```

### Chat (streaming)

```bash
curl -N -X POST http://localhost:5000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "read the first 5 lines of main.py"}'
```

Returns newline-delimited JSON:

```
{"tool_call": {"tool": "read_file", "input": "{'path': 'main.py', 'start_line': 0, 'end_line': 5}"}}
{"chunk": "Here are the first 5 lines of main.py:\n..."}
{"done": true, "full_response": "Here are the first 5 lines of main.py:\n..."}
```

### Set system prompt

```bash
curl -X POST http://localhost:5000/api/system \
  -H 'Content-Type: application/json' \
  -d '{"system_prompt": "You are a code review assistant. Use the filesystem tools to read and analyze code."}'
```

### View / clear chat history

```bash
# view
curl http://localhost:5000/api/history

# clear
curl -X DELETE http://localhost:5000/api/history
```

## Tools Reference

| # | Tool | Required Params | Description |
|---|------|----------------|-------------|
| 0 | `read_file` | `path` | Read file contents with line numbers |
| 1 | `file_info` | `path` | File metadata (size, modified, line count) |
| 2 | `list_dir` | — | List directory contents with glob |
| 3 | `tree` | — | Directory tree visualization |
| 4 | `write_file` | `path`, `content` | Write/create a file |
| 5 | `append_file` | `path`, `content` | Append to a file |
| 6 | `replace_in_file` | `path`, `old`, `new` | Find & replace in a file |
| 7 | `insert_at_line` | `path`, `line_number`, `content` | Insert text at line |
| 8 | `delete_lines` | `path`, `start`, `end` | Delete line range |
| 9 | `copy_file` | `src`, `dst` | Copy file or directory |
| 10 | `move_file` | `src`, `dst` | Move/rename file |
| 11 | `delete_file` | `path` | Delete a file |
| 12 | `make_dir` | `path` | Create directory tree |
| 13 | `grep` | `pattern` | Regex search across files |
| 14 | `find_files` | — | Find files by name/ext/content |
| 15 | `find_definition` | `symbol` | Find function/class definitions |
| 16 | `web_search` | `query` | DuckDuckGo search |
| 17 | `fetch_url` | `url` | Fetch and extract URL content |
| 18 | `ebay_search` | `query` | Search eBay active listings |
| 19 | `ebay_sold_search` | `query` | Search eBay sold listings |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/models` | List Ollama models |
| `POST` | `/api/models` | Select a model |
| `GET` | `/api/tools` | Get tool browser state |
| `POST` | `/api/tools/select` | Select tool (`>`) |
| `POST` | `/api/tools/deselect` | Deselect tool (`<`) |
| `GET` | `/api/tools/<index>` | Tool detail with params |
| `GET` | `/api/system` | Get system prompt |
| `POST` | `/api/system` | Set system prompt |
| `POST` | `/api/chat` | Send message (sync) |
| `POST` | `/api/chat/stream` | Send message (NDJSON stream) |
| `GET` | `/api/history` | Get chat history |
| `DELETE` | `/api/history` | Clear chat history |
