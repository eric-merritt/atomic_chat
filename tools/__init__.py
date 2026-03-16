"""Tool registry — grouped by agent domain."""

from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS, FLOW_TOOLS
from tools.torrent import TORRENT_TOOLS

ALL_TOOLS = FILESYSTEM_TOOLS + CODESEARCH_TOOLS + WEB_TOOLS + MARKETPLACE_TOOLS + FLOW_TOOLS + TORRENT_TOOLS

# Category registry: ordered dict of {category_name: [tool_objects]}
TOOL_CATEGORIES = {
    "Filesystem": FILESYSTEM_TOOLS,
    "Code Search": CODESEARCH_TOOLS,
    "Web": WEB_TOOLS,
    "Marketplace": MARKETPLACE_TOOLS,
    "Flows": FLOW_TOOLS,
    "Torrents": TORRENT_TOOLS,
}

# Default selection: filesystem + web_search, fetch_url, download_image
DEFAULT_SELECTED = set()
for t in FILESYSTEM_TOOLS:
    DEFAULT_SELECTED.add(t.name)
for t in WEB_TOOLS:
    if t.name in ("web_search", "fetch_url", "download_image"):
        DEFAULT_SELECTED.add(t.name)
