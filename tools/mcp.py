"""MCP tools: connect to Model Context Protocol servers."""

import asyncio
import json
from langchain.tools import tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tools._output import tool_result, retry


async def _list_mcp_tools(url: str) -> list[dict]:
    """Connect to an MCP server and list its tools."""
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = []
            for t in result.tools:
                tool_info = {
                    "name": t.name,
                    "description": t.description or "",
                }
                if t.inputSchema:
                    tool_info["inputSchema"] = t.inputSchema
                tools.append(tool_info)
            return tools


@tool("connect_to_mcp")
@retry()
def connect_to_mcp(url: str) -> str:
    """Connect to an MCP server and retrieve its available tools.

    WHEN TO USE: When you need to discover tools available on an MCP server.
    WHEN NOT TO USE: When you already know which tools are available.

    Args:
        url: Full URL of the MCP server endpoint. Must start with http:// or https://.

    Output format:
        {"status": "success", "data": {"url": "...", "tools": [...]}, "error": ""}
    """
    if not url or not url.startswith(("http://", "https://")):
        return tool_result(error="url must start with http:// or https://")

    # Ensure URL ends with / for MCP streamable HTTP
    if not url.endswith("/"):
        url = url + "/"

    try:
        tools = asyncio.run(_list_mcp_tools(url))
    except Exception as e:
        return tool_result(error=f"Failed to connect to MCP server: {e}")

    return tool_result(data={"url": url, "tools": tools})


MCP_TOOLS = [connect_to_mcp]
