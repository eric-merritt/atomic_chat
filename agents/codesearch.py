"""Code search agent — HTTP tool server for grep, find, definition lookup.

Port: 8102
Tools: 3 code search tools
No LLM. Pure tool execution.
"""

from agents.base import create_tool_server
from tools.codesearch import CODESEARCH_TOOLS
from config import AGENT_PORTS


def create_app():
    return create_tool_server(
        name="codesearch",
        tools=CODESEARCH_TOOLS,
        port=AGENT_PORTS["codesearch"],
    )


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=AGENT_PORTS["codesearch"])
