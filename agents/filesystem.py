"""Filesystem agent — MCP server for file read/write/manage operations.

Port: 8101
Tools: 13 filesystem tools
Model: small abliterated (configured in config.py)
"""

from agents.base import create_mcp_agent
from tools.filesystem import FILESYSTEM_TOOLS
from config import AGENT_PORTS

SYSTEM_PROMPT = """Execute filesystem operations exactly as requested.
Return raw file contents, directory listings, or operation confirmations.
No commentary on file contents. No suggestions about what to do next."""


def create_app():
    return create_mcp_agent(
        name="filesystem-agent",
        tools=FILESYSTEM_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["filesystem"])
