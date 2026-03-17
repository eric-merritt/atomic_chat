"""Marketplace agent — MCP server for eBay, Amazon, Craigslist searches.

Port: 8104
Tools: 6 platform search tools (flow tools are owned by the dispatcher)
Model: medium abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.marketplace import MARKETPLACE_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Search marketplace platforms and return structured listing data.
Every listing MUST include: title, price, shipping, url, platform.
Return results as JSON arrays. No analysis. No filtering. No opinions.
No commentary about what the listings mean or whether they are good deals."""


def create_app():
    return create_mcp_agent(
        name="marketplace-agent",
        tools=MARKETPLACE_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["marketplace"])
