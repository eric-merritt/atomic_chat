"""Shared factory for creating MCP agent servers.

Each subagent is a FastMCP server with streamable-http transport.
Tools are bridged from LangChain @tool functions to MCP tool handlers.
"""

import inspect
import typing

from mcp.server.fastmcp import FastMCP


PROMPT_DISCIPLINE = """You are a tool executor. You receive parameters, call tools, return raw structured results.

Rules:
- Do not speculate about user intent. Do not hypothesize motivations.
- Execute the request. Return the result.
- Never describe the format of data. Never describe what data looks like.
- Process data and return actionable output.
- No preamble. No analysis. No suggestions. No follow-up questions.
- Return JSON only when returning structured data.
- If you cannot process the request, return an error with what went wrong."""


def create_mcp_agent(
    name: str,
    tools: list,
    system_prompt: str = "",
    stateless: bool = True,
) -> FastMCP:
    """Create a FastMCP server with LangChain tools bridged to MCP tools.

    Args:
        name: Agent name (used in MCP server identification).
        tools: List of LangChain @tool decorated functions.
        system_prompt: Additional system prompt (appended to prompt discipline).
        stateless: If True, use stateless HTTP mode (recommended).

    Returns:
        Configured FastMCP instance ready to run.
    """
    full_prompt = PROMPT_DISCIPLINE
    if system_prompt:
        full_prompt += "\n\n" + system_prompt

    mcp = FastMCP(
        name,
        stateless_http=stateless,
        json_response=True,
    )

    # Bridge each LangChain tool to an MCP tool
    for lc_tool in tools:
        _register_lc_tool(mcp, lc_tool)

    # Health check as a simple HTTP-accessible resource
    @mcp.resource(f"health://{name}")
    def health() -> str:
        return f'{{"status": "ok", "agent": "{name}", "tools": {len(tools)}}}'

    # Store the system prompt as a retrievable MCP resource
    @mcp.resource(f"config://system-prompt/{name}")
    def get_system_prompt() -> str:
        return full_prompt

    return mcp


def _register_lc_tool(mcp: FastMCP, lc_tool) -> None:
    """Bridge a LangChain tool to an MCP tool handler.

    Extracts name, description, and schema from the LangChain tool
    and registers an equivalent MCP tool that delegates to lc_tool.invoke().
    Uses model_json_schema() (Pydantic v2) and preserves default values.
    """
    tool_name = lc_tool.name
    tool_desc = lc_tool.description or ""

    # Extract the parameter schema from LangChain tool (Pydantic v2)
    schema = lc_tool.args_schema.model_json_schema() if lc_tool.args_schema else {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build parameter list with types and defaults
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    # Build inspect.Parameter objects for proper function signature
    params_list = []
    for pname, pinfo in properties.items():
        ptype = pinfo.get("type", "string")
        py_type = type_map.get(ptype, str)

        if pname in required:
            param = inspect.Parameter(
                pname,
                inspect.Parameter.KEYWORD_ONLY,
                annotation=py_type,
            )
        else:
            default = pinfo.get("default")
            param = inspect.Parameter(
                pname,
                inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=typing.Optional[py_type],
            )
        params_list.append(param)

    # Create an MCP tool function that delegates to the LangChain tool
    def make_handler(lt, sig):
        async def handler(**kwargs) -> str:
            # Remove None values for optional params not provided
            cleaned = {k: v for k, v in kwargs.items() if v is not None}
            result = lt.invoke(cleaned)
            return str(result)

        handler.__name__ = tool_name
        handler.__doc__ = tool_desc
        handler.__signature__ = sig
        return handler

    sig = inspect.Signature(
        parameters=params_list,
        return_annotation=str,
    )
    handler = make_handler(lc_tool, sig)
    mcp.tool()(handler)
