"""Code search agent — MCP server for grep, find, definition lookup.

Port: 8102
Tools: 3 code search tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.codesearch import CODESEARCH_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Search code and return matching results with full file paths and line numbers.
Return raw search results. No interpretation of what the code does.
No suggestions about code quality or improvements."""


def create_app():
    return create_mcp_agent(
        name="codesearch-agent",
        tools=CODESEARCH_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["codesearch"])
