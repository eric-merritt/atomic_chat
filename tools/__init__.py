"""Tool registry — grouped by agent domain."""

from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS, FLOW_TOOLS

ALL_TOOLS = FILESYSTEM_TOOLS + CODESEARCH_TOOLS + WEB_TOOLS + MARKETPLACE_TOOLS + FLOW_TOOLS
