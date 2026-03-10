"""Test marketplace agent creation."""
from mcp.server.fastmcp import FastMCP


def test_marketplace_agent_creates():
    from agents.marketplace import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "marketplace-agent"
