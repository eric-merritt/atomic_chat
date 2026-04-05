# MCP Conversion: tools_server.py

**Date:** 2026-03-22
**Status:** Approved

## Summary

Replace the custom REST API in `tools_server.py` with a true MCP (Model Context Protocol) server using the `mcp` Python SDK's `FastMCP` class and Streamable HTTP transport. Update `prepass.py` to use the MCP client SDK instead of raw HTTP. Update `tools/mcp.py` to speak MCP protocol.

## Design Decisions

- **Transport:** Streamable HTTP (stateless, JSON responses) — works through existing nginx/TLS setup
- **Auth:** None for now (matches current REST API behavior)
- **Tool scope:** All tools from `ALL_TOOLS` — 1:1 parity with current REST API
- **Path:** Root `/` serves MCP — no `/mcp` sub-path
- **Port:** 5100 (unchanged)
- **SDK version:** mcp 1.26.0 (FastMCP v1 API)

## Changes

### 1. `tools_server.py` — Full rewrite

Replace Flask app with `FastMCP` server:
- Create `FastMCP("ToolServer", stateless_http=True, json_response=True)`
- Set `streamable_http_path="/"` so MCP is served at root
- Iterate `ALL_TOOLS` (LangChain `BaseTool` objects) and register each as an MCP tool
- For each tool: extract name, description, and `args_schema` (Pydantic model) to build MCP tool registration
- Tool execution calls `tool.invoke(params)` and returns the result string
- Run with `transport="streamable-http"`, `host="0.0.0.0"`, `port=5100`

### 2. `prepass.py` — Switch to MCP client

Replace `load_tool_index()`:
- Use `streamable_http_client` + `ClientSession` to connect to `TOOLS_SERVER_URL`
- Call `session.list_tools()` to get tool schemas
- Build compact index from MCP tool objects (`.name`, `.description`)
- Wrap in `asyncio.run()` since the rest of the codebase is sync

### 3. `tools/mcp.py` — Update `connect_to_mcp`

Replace `requests.get()` with MCP client SDK:
- Use `streamable_http_client` + `ClientSession`
- Call `session.list_tools()` and return structured tool list
- Wrap in `asyncio.run()`

### 4. `start.sh` — No changes needed

Same command (`uv run python tools_server.py`), same port.

### 5. Tests — Update imports

`test_integration_accounting.py` imports `tools_app` from `tools_server` — update to test against the MCP server.
