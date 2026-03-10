# Subagent Architecture Design

## Problem

The current monolithic agent binds 27 tools to a single Ollama model. This causes:
- Poor tool selection accuracy with qwen models
- Intent speculation ("Maybe the user wants X because Y...")
- Data narration ("This appears to be a JSON array of listings possibly from...")
- Over-summarization instead of returning actionable data

## Solution

Break the monolithic agent into 5 specialized subagents exposed as MCP HTTP servers behind nginx. A dispatcher/analyst agent orchestrates workflows and does all reasoning.

## Architecture

```
Continue.dev ──┐
               ├──► nginx (reverse proxy)
Your Chat UI ──┘         │
                          ├── /agents/filesystem   (MCP server, port 8101)
                          ├── /agents/codesearch    (MCP server, port 8102)
                          ├── /agents/web           (MCP server, port 8103)
                          ├── /agents/marketplace   (MCP server, port 8104)
                          └── /agents/dispatcher    (MCP server, port 8105)
                                    │
                                    ├──► filesystem agent (internal HTTP)
                                    ├──► codesearch agent (internal HTTP)
                                    ├──► web agent (internal HTTP)
                                    └──► marketplace agent (internal HTTP)
```

All agents are independently accessible. Continue.dev and the chat UI can talk to any agent directly or go through the dispatcher for orchestrated workflows.

## Agents

### 1. Filesystem Agent (port 8101)
- **Tools:** read_file, file_info, list_dir, tree, write_file, append_file, replace_in_file, insert_at_line, delete_lines, copy_file, move_file, delete_file, make_dir
- **Model:** Small abliterated model (e.g., qwen2.5-coder-abliterate:7b)
- **Prompt:** Tool executor. Return raw results. No summaries, no commentary.

### 2. Code Search Agent (port 8102)
- **Tools:** grep, find_files, find_definition
- **Model:** Small abliterated model
- **Prompt:** Return matching lines/files with full paths and line numbers. No interpretation.

### 3. Web Agent (port 8103)
- **Tools:** web_search, fetch_url
- **Model:** Small abliterated model
- **Prompt:** Fetch web content. Return raw text/HTML. No summarization.

### 4. Marketplace Agent (port 8104)
- **Tools:** ebay_search, ebay_sold_search, ebay_deep_scan, amazon_search, craigslist_search, craigslist_multi_search
- **Model:** Medium abliterated model (e.g., qwen2.5-coder-abliterate:14b)
- **Prompt:** Return structured listing data as JSON arrays. Every listing must include: title, price, shipping, url, platform. No analysis, no filtering, no opinions.

### 5. Dispatcher/Analyst (port 8105)
- **Tools:** None directly — has tool definitions loaded for planning, delegates all execution to subagents
- **Model:** Strongest available abliterated model
- **Responsibilities:**
  - Parse user intent and decompose into subagent calls
  - Fan out requests with rate limiting
  - LLM self-eval on returned data quality
  - Retry with modified parameters if quality check fails (max 2 retries)
  - Analyze, deduplicate, rank, present results
  - Contains all domain knowledge (GPU generations, pricing rules, marketplace selection)

## Prompt Discipline

All agents enforce strict output rules:

**Subagents (collectors):**
> "You are a tool executor. You receive parameters, call tools, return raw structured results. No preamble. No analysis. No suggestions. No follow-up questions. Return JSON only."

**Anti-patterns killed in all prompts:**
> "Do not speculate about user intent. Do not hypothesize motivations. Execute the request. Return the result."
> "Never describe the format of data. Never describe what data looks like. Process it and return actionable output."

**Dispatcher:**
> "You have knowledge of all available tools across all agents. Plan which agents to call with what parameters. When results come back, evaluate quality. When presenting final results, extract and present the actual data. Never describe data formats. Never speculate about intent. Never ask clarifying questions you can resolve yourself."

## Data Flow

### Subagent Request/Response Contract

```json
Request:  { "action": "ebay_search", "params": {"query": "RTX 3060", "max_results": 20} }
Response: { "status": "ok", "data": [...], "tool": "ebay_search", "count": 20 }
Error:    { "status": "error", "error": "connection timeout", "tool": "ebay_search" }
```

### Rate Limiting

- **Parallel across platforms** (eBay + Amazon + Craigslist run simultaneously)
- **Sequential within the same platform** with configurable cooldown
- Default 6 seconds between same-platform requests

```
User: "find GPU deals"
  │
  ├── ebay_search → eval → 6s → ebay_sold_search → eval → 6s → ebay_deep_scan
  │                                                              (if needed)
  ├── amazon_search → eval                              ← parallel with eBay
  │
  └── craigslist_multi_search → eval                    ← parallel with both
```

### Quality Control

For each subagent response, the dispatcher performs LLM self-eval:
- "Is this valid structured listing data with prices and URLs, or is it garbage/empty/malformed?"
- If bad: retry that specific subagent with modified params (broader query, different page, etc.), max 2 retries
- If still bad after retries: mark that source as unavailable, proceed with what worked

### Rate Limit Configuration

```python
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}
```

## Project Structure

```
agentic_w_langchain_ollama/
├── agents/
│   ├── base.py              # Shared MCP server boilerplate, prompt discipline
│   ├── filesystem.py         # Port 8101
│   ├── codesearch.py         # Port 8102
│   ├── web.py                # Port 8103
│   ├── marketplace.py        # Port 8104
│   └── dispatcher.py         # Port 8105
├── tools/
│   ├── __init__.py           # Re-exports grouped tool lists
│   ├── filesystem.py         # read_file, file_info, list_dir, tree, write/edit ops
│   ├── codesearch.py         # grep, find_files, find_definition
│   ├── web.py                # web_search, fetch_url
│   └── marketplace.py        # ebay_*, amazon_*, craigslist_*
├── config.py                 # Model assignments, ports, rate limits
├── main.py                   # Chat UI (updated to call agents via HTTP)
├── tools.py                  # Backwards compat, imports from tools/
└── nginx/
    └── agents.conf           # nginx reverse proxy config
```

## Integration

### Continue.dev
- Each agent registered as an MCP server in Continue.dev config
- Chat-based invocation routes to the right agent
- Inline/contextual use: highlight data in editor, invoke agent on it

### Chat UI
- Existing main.py updated to call agents via HTTP instead of building monolithic agent
- Can target any agent directly or use dispatcher for orchestrated workflows

## Models

- All agents use abliterated open-source Ollama models
- Model assignment is per-agent and configurable
- Smaller models for simple ops (filesystem, code search, web)
- Medium models for marketplace (needs correct tool arg handling)
- Strongest model for dispatcher (does all reasoning)
