"""Shared factory for creating plain HTTP tool servers.

Each subagent is a Starlette app that exposes LangChain tools as
POST /call endpoints. No MCP. No LLM. Pure tool execution.
"""

import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def create_tool_server(
    name: str,
    tools: list,
    port: int = 8000,
) -> Starlette:
    """Create a plain HTTP server that exposes LangChain tools.

    Args:
        name: Agent name (for identification).
        tools: List of LangChain @tool decorated functions.
        port: Port number (stored as app metadata, used by caller).

    Returns:
        Starlette app ready to run with uvicorn.
    """
    # Index tools by name for dispatch
    tool_map = {t.name: t for t in tools}

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "agent": name,
            "tools": list(tool_map.keys()),
        })

    async def list_tools(request: Request) -> JSONResponse:
        """Return tool names and descriptions."""
        result = []
        for t in tools:
            schema = t.args_schema.model_json_schema() if t.args_schema else {}
            result.append({
                "name": t.name,
                "description": (t.description or "").split("\n")[0],
                "params": schema.get("properties", {}),
                "required": schema.get("required", []),
            })
        return JSONResponse(result)

    async def call_tool(request: Request) -> JSONResponse:
        """Call a tool by name. Body: {"tool": "name", "params": {...}}"""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"status": "error", "error": "Invalid JSON"}, status_code=400)

        tool_name = body.get("tool", "")
        params = body.get("params", {})

        if tool_name not in tool_map:
            return JSONResponse(
                {"status": "error", "error": f"Unknown tool: {tool_name}"},
                status_code=404,
            )

        try:
            result = tool_map[tool_name].invoke(params)
            return JSONResponse({"status": "ok", "data": str(result), "tool": tool_name})
        except Exception as e:
            return JSONResponse(
                {"status": "error", "error": str(e), "tool": tool_name},
                status_code=500,
            )

    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/tools", list_tools, methods=["GET"]),
            Route("/call", call_tool, methods=["POST"]),
        ],
    )
    app.state.name = name
    app.state.port = port
    return app
