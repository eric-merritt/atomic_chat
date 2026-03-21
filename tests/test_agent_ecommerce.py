"""Test ecommerce agent creation."""
from mcp.server.fastmcp import FastMCP


def test_ecommerce_agent_creates():
    from agents.ecommerce import create_app
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "ecommerce-agent"
