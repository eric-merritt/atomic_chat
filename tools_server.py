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

from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

# Snapshot qwen-agent's built-in tools BEFORE importing our package, so we can
# exclude them reliably by identity rather than a hand-maintained name list
# (which drifted: it missed simple_doc_parser/front_page_search/hybrid_search/
# keyword_search/vector_search/extract_doc_vocabulary/image_*/web_search, letting
# qwen's doc tools leak to the top of the MCP tool list).
_BUILTIN_TOOLS = set(QW_TOOL_REGISTRY.keys())

import tools  # noqa: E402,F401 — triggers @register_tool side-effects for our tools

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

def _register_qwen_tool(tool_cls):
  """Register a qwen-agent BaseTool subclass as an MCP tool.

  Dynamically creates a function with the correct parameter signature
  so FastMCP can introspect it properly, then registers it as an MCP tool.
  """
  name = tool_cls.name
  description = tool_cls.description or ""

  schema = getattr(tool_cls, 'parameters', {}) or {}
  properties = schema.get("properties", {})
  required_set = set(schema.get("required", []))

  # Build inspect.Parameter list for the function signature
  params = []
  for pname, pinfo in properties.items():
    py_type = _TYPE_MAP.get(pinfo.get("type", "string"), str)
    is_required = pname in required_set
    default = inspect.Parameter.empty

    if not is_required:
      default = pinfo.get("default")
      if default is None:
        default = None
      py_type = typing.Optional[py_type]

    params.append(inspect.Parameter(
      pname,
      inspect.Parameter.POSITIONAL_OR_KEYWORD,
      default=default,
      annotation=py_type,
    ))

  sig = inspect.Signature(params, return_annotation=str)

  # Build the wrapper — instantiates tool and calls it with JSON params
  async def _wrapper(*args, _cls=tool_cls, _sig=sig, **kwargs):
    bound = _sig.bind(*args, **kwargs)
    bound.apply_defaults()
    call_args = {k: v for k, v in bound.arguments.items() if v is not None}
    try:
      result = _cls().call(json.dumps(call_args))
      return json.dumps(result) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
      return json.dumps({"status": "error", "data": None, "error": str(e)})

  _wrapper.__name__ = name
  _wrapper.__qualname__ = name
  _wrapper.__doc__ = description
  _wrapper.__signature__ = sig
  _wrapper.__annotations__ = {p.name: p.annotation for p in params}
  _wrapper.__annotations__["return"] = str

  mcp.tool(name=name, description=description)(_wrapper)


# Register all custom qwen-agent tools as MCP tools (skip built-ins)
_registered = 0
for _name, _cls in QW_TOOL_REGISTRY.items():
  if _name in _BUILTIN_TOOLS:
    continue
  try:
    _register_qwen_tool(_cls)
    logger.info("Registered MCP tool: %s", _name)
    _registered += 1
  except Exception as e:
    logger.error("Failed to register tool %s: %s", _name, e)


def main():
  print(f"Starting MCP Tool Server on http://0.0.0.0:{PORT}")
  print(f"  {_registered} tools registered")
  print(f"  Transport: Streamable HTTP (stateless, JSON responses)")
  print(f"  Connect with any MCP client to https://tools.eric-merritt.com/")
  mcp.run(transport="streamable-http")


if __name__ == "__main__":
  main()
