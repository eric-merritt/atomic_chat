"""MCP Tool Server — serves all tools via Model Context Protocol.

Hosted at https://tools.eric-merritt.com via nginx proxy to localhost:5100.

Uses Streamable HTTP transport (stateless, JSON responses) so any
MCP-compatible client (Claude Desktop, Claude Code, etc.) can connect.
"""

import inspect
import json
import logging
import typing
from mcp.server.fastmcp import FastMCP

from tools import ALL_TOOLS

logger = logging.getLogger(__name__)

PORT = 5100

# Create MCP server — stateless HTTP with JSON responses, served at /
mcp = FastMCP(
    "ToolServer",
    host="0.0.0.0",
    port=PORT,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)

# Type mapping from JSON Schema types to Python types
_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _register_langchain_tool(lc_tool):
    """Register a LangChain BaseTool as an MCP tool.

    Dynamically creates a function with the correct parameter signature
    so FastMCP can introspect it properly, then registers it as an MCP tool.
    """
    name = lc_tool.name
    description = lc_tool.description or ""

    # Extract parameter schema from LangChain tool
    if lc_tool.args_schema:
        schema = lc_tool.args_schema.model_json_schema()
        properties = schema.get("properties", {})
        required_set = set(schema.get("required", []))
    else:
        properties = {}
        required_set = set()

    # Build inspect.Parameter list for the function signature
    params = []
    for pname, pinfo in properties.items():
        py_type = _TYPE_MAP.get(pinfo.get("type", "string"), str)
        is_required = pname in required_set
        default = inspect.Parameter.empty

        if not is_required:
            default = pinfo.get("default")
            if default is None:
                default = None  # explicit None default for optional params
            py_type = typing.Optional[py_type]

        params.append(inspect.Parameter(
            pname,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=default,
            annotation=py_type,
        ))

    sig = inspect.Signature(params, return_annotation=str)

    # Build the wrapper function that delegates to lc_tool.invoke()
    # We capture lc_tool in the closure via default arg to avoid late-binding issues
    async def _wrapper(*args, _tool=lc_tool, _sig=sig, **kwargs):
        # Bind positional+keyword args to parameter names
        bound = _sig.bind(*args, **kwargs)
        bound.apply_defaults()
        call_args = dict(bound.arguments)
        # Remove None values for optional params not provided
        call_args = {k: v for k, v in call_args.items() if v is not None}
        try:
            result = _tool.invoke(call_args)
            return str(result)
        except Exception as e:
            return json.dumps({"status": "error", "data": None, "error": str(e)})

    # Set function metadata so FastMCP introspects correctly
    _wrapper.__name__ = name
    _wrapper.__qualname__ = name
    _wrapper.__doc__ = description
    _wrapper.__signature__ = sig
    _wrapper.__annotations__ = {p.name: p.annotation for p in params}
    _wrapper.__annotations__["return"] = str

    # Register with MCP server
    mcp.tool(name=name, description=description)(_wrapper)


# Register all LangChain tools as MCP tools
for _lc_tool in ALL_TOOLS:
    try:
        _register_langchain_tool(_lc_tool)
        logger.info("Registered MCP tool: %s", _lc_tool.name)
    except Exception as e:
        logger.error("Failed to register tool %s: %s", _lc_tool.name, e)


def main():
    print(f"Starting MCP Tool Server on http://0.0.0.0:{PORT}")
    print(f"  {len(ALL_TOOLS)} tools registered")
    print(f"  Transport: Streamable HTTP (stateless, JSON responses)")
    print(f"  Connect with any MCP client to https://tools.eric-merritt.com/")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
