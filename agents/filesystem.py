"""Filesystem agent — HTTP tool server for file read/write/manage operations.

Port: 8101
Tools: 13 filesystem tools
No LLM. Pure tool execution.
"""

from agents.base import create_tool_server
from tools.filesystem import FILESYSTEM_TOOLS
from config import AGENT_PORTS


def create_app():
    return create_tool_server(
        name="filesystem",
        tools=FILESYSTEM_TOOLS,
        port=AGENT_PORTS["filesystem"],
    )


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=AGENT_PORTS["filesystem"])
