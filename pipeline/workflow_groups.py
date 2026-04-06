"""Static registry of workflow groups for tool curation.

Each group maps a human-readable name to a list of tool names and a short
tooltip. The Tool Curator recommends groups — not individual tools.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowGroup:
    tools: list[str]
    tooltip: str


WORKFLOW_GROUPS: dict[str, WorkflowGroup] = {
    "Filesystem": WorkflowGroup(
        tools=["fs_read", "fs_info", "fs_ls", "fs_tree", "fs_write", "fs_append",
               "fs_replace", "fs_insert_at_line", "fs_delete", "fs_copy", "fs_move",
               "fs_create_directory"],
        tooltip="File reading, writing, and directory operations",
    ),
    "Code Search": WorkflowGroup(
        tools=["cs_grep", "cs_find", "cs_def"],
        tooltip="Search code by pattern, filename, or symbol",
    ),
    "Web Tools": WorkflowGroup(
        tools=["www_ddg", "www_fetch", "www_scrape", "www_cookies",
               "www_find_all", "www_find_dl", "www_find_routes",
               "www_browse", "www_query", "www_click"],
        tooltip="Web scraping, search, and navigation",
    ),
    "Ecommerce": WorkflowGroup(
        tools=["ec_search", "ec_enrich"],
        tooltip="Product search across eBay, Amazon, and Craigslist",
    ),
    "OnlyFans": WorkflowGroup(
        tools=["of_extract", "of_extract_all",
               "of_scroll_convos", "of_scroll_msgs",
               "of_save_media"],
        tooltip="Creator discovery, profiles, and media management",
    ),
    "Torrent": WorkflowGroup(
        tools=["bt_search", "bt_download", "bt_plugins",
               "bt_toggle_plugin", "bt_add", "bt_active"],
        tooltip="Torrent search, download, and management",
    ),
    "MCP": WorkflowGroup(
        tools=["mcp_connect"],
        tooltip="Connect to external MCP tool servers",
    ),
    "Accounting": WorkflowGroup(
        tools=["fa_ledger", "fa_new_acct", "fa_ls_accts",
               "fa_acct_bal", "fa_update_acct",
               "fa_tx_new", "fa_tx_search",
               "fa_tx_void", "fa_acct_det",
               "fa_new_item", "fa_receive",
               "fa_ls_items", "fa_rm_item",
               "fa_tx_sale",
               "fa_value", "fa_close",
               "fa_stmt"],
        tooltip="Double-entry bookkeeping and financial reports",
    ),
}


TOOL_REF: dict[str, str] = {
    # Filesystem
    "fs_read":             "read file",
    "fs_info":             "file info",
    "fs_ls":               "list directory",
    "fs_tree":             "directory tree",
    "fs_write":            "write file",
    "fs_append":           "append file",
    "fs_replace":          "find replace",
    "fs_insert_at_line":   "insert lines",
    "fs_delete":           "delete file",
    "fs_copy":             "copy file",
    "fs_move":             "move file",
    "fs_create_directory": "make directory",
    # Code Search
    "cs_grep":             "search code",
    "cs_find":             "find file",
    "cs_def":              "find definition",
    # Web
    "www_ddg":          "web search",
    "www_cookies":         "set cookies",
    "www_fetch":           "fetch url",
    "www_scrape":          "scrape page",
    "www_find_all":        "find elements",
    "www_find_dl":         "find downloads",
    "www_find_routes":     "find routes",
    "www_browse":          "selenium browse",
    "www_query":           "query page",
    "www_click":           "click element",
    # Ecommerce
    "ec_search":           "search listings (ebay/amazon/cl)",
    "ec_enrich":           "enrich data",
    # OnlyFans
    "of_extract":          "extract media",
    "of_extract_all":      "extract all",
    "of_scroll_convos":    "scroll conversations",
    "of_scroll_msgs":      "scroll messages",
    "of_save_media":       "save media file",
    # Torrent
    "bt_search":           "search torrents",
    "bt_download":         "download torrent",
    "bt_plugins":          "list plugins",
    "bt_toggle_plugin":    "toggle plugin",
    "bt_add":              "add torrent",
    "bt_active":           "active downloads",
    # MCP
    "mcp_connect":         "connect server",
    # Accounting
    "fa_ledger":           "create ledger",
    "fa_new_acct":         "create account",
    "fa_ls_accts":         "list accounts",
    "fa_acct_bal":         "account balance",
    "fa_update_acct":      "update account",
    "fa_tx_new":           "journalize transaction",
    "fa_tx_search":        "search journal",
    "fa_tx_void":          "void transaction",
    "fa_acct_det":         "account history",
    "fa_new_item":         "register item",
    "fa_receive":          "receive inventory",
    "fa_ls_items":         "list items",
    "fa_rm_item":          "remove item",
    "fa_tx_sale":          "inventory sale (FIFO/LIFO)",
    "fa_value":            "inventory value",
    "fa_close":            "close period",
    "fa_stmt":             "financial statement",
}


def tool_ref_for_group(group_name: str) -> str:
    """Return a compact reference string for a group's tools."""
    group = WORKFLOW_GROUPS.get(group_name)
    if not group:
        return ""
    return ", ".join(f"{t}: {TOOL_REF.get(t, '?')}" for t in group.tools)


def build_tool_reference(tool_names: list[str]) -> str:
    """Build a system-prompt-ready tool reference with params.

    Format per tool:
      tool_name(param1, param2, ...) — short description
    Grouped by category.
    """
    from qwen_agent.tools.base import TOOL_REGISTRY as QW

    # Group tools by their workflow group
    grouped: dict[str, list[str]] = {}
    for name in tool_names:
        g = group_for_tool(name)
        label = g or "Other"
        grouped.setdefault(label, []).append(name)

    lines = []
    for group_label, names in grouped.items():
        lines.append(f"[{group_label}]")
        for name in names:
            desc = TOOL_REF.get(name, "")
            cls = QW.get(name)
            if cls:
                props = getattr(cls, 'parameters', {}).get('properties', {})
                required = set(getattr(cls, 'parameters', {}).get('required', []))
                param_parts = []
                for p in props:
                    param_parts.append(f"{p}*" if p in required else p)
                params_str = ", ".join(param_parts)
            else:
                params_str = ""
            lines.append(f"  {name}({params_str}) — {desc}")
        lines.append("")
    return "\n".join(lines).rstrip()


def tools_for_groups(group_names: list[str]) -> list[str]:
    """Return flat list of tool names for the given group names."""
    tools = []
    for name in group_names:
        group = WORKFLOW_GROUPS.get(name)
        if group:
            tools.extend(group.tools)
    return tools


def group_for_tool(tool_name: str) -> str | None:
    """Return the group name a tool belongs to, or None."""
    for name, group in WORKFLOW_GROUPS.items():
        if tool_name in group.tools:
            return name
    return None
