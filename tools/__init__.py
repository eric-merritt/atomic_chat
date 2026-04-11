"""Tool registry — grouped by agent domain.

All tool modules use qwen-agent's @register_tool decorator.
Importing each module triggers registration in TOOL_REGISTRY.
ALL_TOOLS is built from the registry after all modules are loaded.
"""

from qwen_agent.tools.base import TOOL_REGISTRY

# Snapshot built-in tool names before our imports
_BUILTIN_TOOLS = set(TOOL_REGISTRY.keys())

# Import each module to trigger @register_tool side effects
import tools.filesystem  # noqa: F401
import tools.web  # noqa: F401
import tools.ecommerce  # noqa: F401
import tools.onlyfans  # noqa: F401
import tools.torrent  # noqa: F401
import tools.mcp  # noqa: F401
import tools.accounting  # noqa: F401

# Build ALL_TOOLS as instantiated tool objects (only our custom tools)
ALL_TOOLS = []
for name, cls in TOOL_REGISTRY.items():
    if name not in _BUILTIN_TOOLS:
        ALL_TOOLS.append(cls())
