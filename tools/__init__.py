"""Tool registry — grouped by agent domain."""

import tools.filesystem  # noqa: F401 — registers filesystem tools via @register_tool
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.ecommerce import ECOMMERCE_TOOLS, FLOW_TOOLS
from tools.onlyfans import ONLYFANS_TOOLS
from tools.torrent import TORRENT_TOOLS
from tools.mcp import MCP_TOOLS
from tools.accounting import ACCOUNTING_TOOLS

ALL_TOOLS = (
    CODESEARCH_TOOLS
    + WEB_TOOLS
    + ECOMMERCE_TOOLS
    + FLOW_TOOLS
    + ONLYFANS_TOOLS
    + TORRENT_TOOLS
    + MCP_TOOLS
    + ACCOUNTING_TOOLS
)
