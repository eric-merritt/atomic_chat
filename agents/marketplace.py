"""Marketplace agent — HTTP tool server for eBay, Amazon, Craigslist searches.

Port: 8104
Tools: marketplace search tools
No LLM. Pure tool execution.
"""

from agents.base import create_tool_server
from tools.marketplace import MARKETPLACE_TOOLS
from config import AGENT_PORTS


def create_app():
    return create_tool_server(
        name="marketplace",
        tools=MARKETPLACE_TOOLS,
        port=AGENT_PORTS["marketplace"],
    )


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=AGENT_PORTS["marketplace"])
