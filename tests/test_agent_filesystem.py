"""Test filesystem agent creation."""
from mcp.server.fastmcp import FastMCP


def test_filesystem_agent_creates():
    from agents.filesystem import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "filesystem-agent"
