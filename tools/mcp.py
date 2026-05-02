import json
import os
import asyncio
import json5

from qwen_agent.tools.base import BaseTool, register_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tools._output import tool_result

_DEFAULT_MCP_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:5100/")


@register_tool("mcp_init_conn")
class MCPInitializeConnection(BaseTool):
    description = 'Connect to an MCP server and list its available tools with their schemas.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': 'URL of the MCP server (must start with http:// or https://).',
            },
        },
        'required': ['url'],
    }

    async def _initialize_connection(self, url: str):
        """Initialize the connection to the MCP server and fetch the available tools."""
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()

                tools = []
                for tool in result.tools:
                    tool_info = {
                        "name": tool.name,
                        "description": tool.description or "",
                    }
                    if tool.inputSchema:
                        try:
                            tool_info["inputSchema"] = json.dumps(tool.inputSchema)
                        except (TypeError, ValueError):
                            pass
                    tools.append(tool_info)

                return tools

    def call(self, params: str, **kwargs) -> dict:
        try:
            params_dict = json5.loads(params)
            url = params_dict['url']
        except (json.JSONDecodeError, KeyError) as e:
            return tool_result(error=f"Invalid input parameters: {str(e)}")

        if not url or not url.startswith(("http://", "https://")):
            return tool_result(error="URL must start with http:// or https://")

        if not url.endswith("/"):
            url = url + "/"

        try:
            tools = asyncio.run(self._initialize_connection(url))
        except Exception as e:
            return tool_result(error=f"Failed to connect to MCP server: {str(e)}")

        return tool_result(data={"url": url, "tools": tools})


@register_tool('mcp_call_tool')
class MCPToolCall(BaseTool):
    """
    A tool that directly calls a specific tool on the MCP server and retrieves the result.
    
    Args:
        url (str): The URL of the MCP server.
        tool_name (str): The name of the tool to be called on the MCP server.
        parameters (dict): The parameters to pass to the specific tool on the MCP server.
    """

    description = 'Call a specific tool on an MCP server with parameters. If url is omitted, defaults to the local tool server.'

    parameters = {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': 'Optional MCP server URL. Defaults to the local tool server.'
            },
            'tool_name': {
                'type': 'string',
                'description': 'The name of the tool to call on the MCP server.'
            },
            'parameters': {
                'type': 'object',
                'description': 'The parameters to pass to the specific tool on the MCP server.'
            }
        },
        'required': ['tool_name', 'parameters'],
    }

    async def _call_remote(self, url: str, tool_name: str, tool_params: dict):
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await session.call_tool(tool_name, tool_params)

    def call(self, params: str, **kwargs) -> dict:
        try:
            params_dict = json5.loads(params)
            url = params_dict.get('url') or _DEFAULT_MCP_URL
            tool_name = params_dict['tool_name']
            tool_params = params_dict['parameters']
        except (json.JSONDecodeError, KeyError) as e:
            return tool_result(error=f"Invalid input parameters: {str(e)}")

        if not url.startswith(("http://", "https://")):
            return tool_result(error="URL must start with http:// or https://")

        if not url.endswith("/"):
            url = url + "/"

        try:
            result = asyncio.run(self._call_remote(url, tool_name, tool_params))
        except Exception as e:
            return tool_result(error=f"Failed to call the tool on MCP server: {str(e)}")

        # Unwrap MCP CallToolResult -> the tool's actual {status, data, error} dict.
        content = getattr(result, 'content', None) or []
        if content:
            first = content[0]
            text = getattr(first, 'text', None)
            if text:
                try:
                    inner = json.loads(text)
                    if isinstance(inner, dict) and 'status' in inner:
                        return inner  # already in tool_result shape
                    return tool_result(data=inner)
                except (json.JSONDecodeError, ValueError):
                    return tool_result(data=text)
        return tool_result(data=str(result))