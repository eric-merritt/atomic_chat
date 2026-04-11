import json
import json5

from qwen_agent.tools.base import BaseTool, register_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from tools._output import tool_result, retry


@register_tool("mcp_init_conn") 
class MCPInitializeConnection(BaseTool):
    """
    This tool initializes the connection to the MCP server and registers the available tools.
    
    Args:
        url (str): The URL of the MCP server.

    Returns:
        list: A list of dictionaries containing tool name, description, and input schema.
    """

    async def _initialize_connection(self, url: str):
        """Initialize the connection to the MCP server and fetch the available tools."""
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()  # Initialize the session with the server
                result = await session.list_tools()  # List tools on the MCP server

                tools = []
                # For each tool, collect the relevant information
                for tool in result.tools:
                    tool_info = {
                        "name": tool.name,
                        "description": tool.description or "",  # Use an empty string if description is missing
                    }

                    # If inputSchema exists, include it in the tool's info
                    if tool.inputSchema:
                        tool_info["inputSchema"] = tool.inputSchema

                    tools.append(tool_info)

                return tools

    @retry()
    async def call(self, params: str, **kwargs) -> dict:
        """
        Initializes the connection to the MCP server and retrieves available tools.
        
        Args:
            params (str): A JSON string containing the URL of the MCP server.

        Returns:
            dict: A result dictionary containing the URL and a list of tools, or an error message.
        """
        try:
            # Load parameters from the provided JSON string
            params_dict = json5.loads(params)
            url = params_dict['url']
        except (json.JSONDecodeError, KeyError) as e:
            return tool_result(error=f"Invalid input parameters: {str(e)}")

        # Validate the URL
        if not url or not url.startswith(("http://", "https://")):
            return tool_result(error="URL must start with http:// or https://")

        # Ensure URL ends with a '/' to support MCP streamable HTTP
        if not url.endswith("/"):
            url = url + "/"

        # Initialize connection and fetch available tools
        try:
            tools = await self._initialize_connection(url)
        except Exception as e:
            return tool_result(error=f"Failed to connect to MCP server: {str(e)}")

        # Return the result containing tools
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

    description = 'Call a specific tool on an MCP server with parameters.'

    parameters = {
        'type': 'object',
        'properties': {
            'url': {
                'type': 'string',
                'description': 'Full URL of the MCP server endpoint. Must start with http:// or https://.'
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
        'required': ['url', 'tool_name', 'parameters'],  # All fields are required
    }

    @retry()
    async def call(self, params: str, **kwargs) -> dict:
        """
        Calls a specific tool with the provided parameters on the MCP server.

        Args:
            params (str): A JSON string containing the URL, tool_name, and parameters.

        Returns:
            dict: A result dictionary containing the response from the tool, or an error message.
        """
        try:
            # Load parameters from the provided JSON string
            params_dict = json5.loads(params)
            url = params_dict['url']
            tool_name = params_dict['tool_name']
            tool_params = params_dict['parameters']
        except (json.JSONDecodeError, KeyError) as e:
            return tool_result(error=f"Invalid input parameters: {str(e)}")

        # Validate the URL
        if not url or not url.startswith(("http://", "https://")):
            return tool_result(error="URL must start with http:// or https://")

        if not url.endswith("/"):
            url = url + "/"

        # Call the tool on the MCP server
        try:
            async with streamable_http_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()  # Initialize the session with the server
                    result = await session.call_tool(tool_name, tool_params)  # Call the specific tool

                    return tool_result(data=result)

        except Exception as e:
            return tool_result(error=f"Failed to call the tool on MCP server: {str(e)}")