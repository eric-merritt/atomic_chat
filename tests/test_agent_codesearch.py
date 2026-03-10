"""Test codesearch agent creation."""
from mcp.server.fastmcp import FastMCP


def test_codesearch_agent_creates():
    from agents.codesearch import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "codesearch-agent"
