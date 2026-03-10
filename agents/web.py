"""Web agent — MCP server for web search and URL fetching.

Port: 8103
Tools: 2 web tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.web import WEB_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Fetch web content and return raw results.
Return the actual text/data from web pages. No summarization.
If a page fails to load, return the error. Do not speculate about why."""


def create_app():
    return create_mcp_agent(
        name="web-agent",
        tools=WEB_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["web"])
