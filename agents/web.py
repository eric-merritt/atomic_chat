"""Web agent — HTTP tool server for web search and URL fetching.

Port: 8103
Tools: 3 web tools
No LLM. Pure tool execution.
"""

from agents.base import create_tool_server
from tools.web import WEB_TOOLS
from config import AGENT_PORTS


def create_app():
    return create_tool_server(
        name="web",
        tools=WEB_TOOLS,
        port=AGENT_PORTS["web"],
    )


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=AGENT_PORTS["web"])
