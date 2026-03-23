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
        tools=["read", "info", "ls", "tree", "write", "append",
               "replace", "insert_at_line", "delete", "copy", "move",
               "create_directory"],
        tooltip="File reading, writing, and directory operations",
    ),
    "Code Search": WorkflowGroup(
        tools=["grep", "find", "definition"],
        tooltip="Search code by pattern, filename, or symbol",
    ),
    "Web Tools": WorkflowGroup(
        tools=["web_search", "fetch_url", "webscrape", "find_all",
               "find_download_link", "find_allowed_routes", "browser_fetch"],
        tooltip="Web scraping, search, and navigation",
    ),
    "Ecommerce": WorkflowGroup(
        tools=["ebay_search", "ebay_sold_search", "ebay_deep_scan",
               "amazon_search", "craigslist_search", "craigslist_multi_search",
               "cross_platform_search", "deal_finder", "enrichment_pipeline"],
        tooltip="Product search across eBay, Amazon, and Craigslist",
    ),
    "OnlyFans": WorkflowGroup(
        tools=["extract_media", "extract_images_and_videos",
               "scroll_conversations", "scroll_messages",
               "save_image", "save_video"],
        tooltip="Creator discovery, profiles, and media management",
    ),
    "Torrent": WorkflowGroup(
        tools=["torrent_search", "torrent_download", "torrent_list_plugins",
               "torrent_enable_plugin", "torrent_add", "torrent_list_active"],
        tooltip="Torrent search, download, and management",
    ),
    "MCP": WorkflowGroup(
        tools=["connect_to_mcp"],
        tooltip="Connect to external MCP tool servers",
    ),
    "Accounting": WorkflowGroup(
        tools=["create_ledger", "create_account", "list_accounts",
               "get_account_balance", "update_account",
               "journalize_transaction", "search_journal",
               "void_transaction", "account_ledger",
               "register_inventory_item", "receive_inventory",
               "list_inventory_items", "deactivate_inventory_item",
               "journalize_fifo_transaction", "journalize_lifo_transaction",
               "inventory_valuation", "close_period",
               "trial_balance", "income_statement", "balance_sheet",
               "cash_flow_statement"],
        tooltip="Double-entry bookkeeping and financial reports",
    ),
}


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
