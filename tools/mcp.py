"""MCP tools: connect to Model Context Protocol servers."""

import requests
from langchain.tools import tool
from tools._output import tool_result, retry


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

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        return tool_result(error=f"Response from {url} is not valid JSON")
    except Exception as e:
        return tool_result(error=f"Failed to connect to MCP server: {e}")

    return tool_result(data={"url": url, "tools": data})


MCP_TOOLS = [connect_to_mcp]
