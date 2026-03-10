"""Test the agent base factory."""
import asyncio
from mcp.server.fastmcp import FastMCP


def test_create_mcp_agent_returns_fastmcp():
    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[],
        system_prompt="You are a test agent.",
    )
    assert isinstance(app, FastMCP)


def test_create_mcp_agent_registers_tools():
    from langchain.tools import tool as lc_tool

    @lc_tool
    def dummy_tool(x: str) -> str:
        """A dummy tool."""
        return x

    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[dummy_tool],
        system_prompt="You are a test agent.",
    )
    # Use the public list_tools() coroutine to verify registration
    tools = asyncio.run(app.list_tools())
    tool_names = [t.name for t in tools]
    assert "dummy_tool" in tool_names


def test_prompt_discipline_included():
    from agents.base import PROMPT_DISCIPLINE
    assert "Do not speculate" in PROMPT_DISCIPLINE
    assert "Never describe the format" in PROMPT_DISCIPLINE


def test_system_prompt_stored_as_resource():
    from agents.base import create_mcp_agent
    app = create_mcp_agent(
        name="test-agent",
        tools=[],
        system_prompt="Custom prompt here.",
    )
    # System prompt is stored as an MCP resource for client retrieval
    resources = asyncio.run(app.list_resources())
    resource_uris = [str(r.uri) for r in resources]
    assert any("system-prompt" in uri for uri in resource_uris)
