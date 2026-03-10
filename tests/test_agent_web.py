"""Test web agent creation."""
from mcp.server.fastmcp import FastMCP


def test_web_agent_creates():
    from agents.web import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "web-agent"
