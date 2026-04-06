# tests/test_integration_accounting.py
"""Test accounting tools are registered and accessible."""


def test_accounting_tools_in_registry():
    from tools import ALL_TOOLS
    names = {t.name for t in ALL_TOOLS}
    assert "fa_ledger" in names
    assert "fa_tx_new" in names
    assert "fa_stmt" in names


def test_accounting_tool_count():
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools.accounting  # noqa: F401
    accounting_names = {
        'fa_ledger', 'fa_new_acct', 'fa_ls_accts', 'fa_acct_bal',
        'fa_update_acct', 'fa_tx_new', 'fa_tx_search', 'fa_tx_void',
        'fa_acct_det', 'fa_new_item', 'fa_receive',
        'fa_ls_items', 'fa_rm_item', 'fa_tx_sale',
        'fa_value', 'fa_close',
        'fa_stmt',
    }
    registered = set(TOOL_REGISTRY.keys())
    assert accounting_names.issubset(registered), f"Missing: {accounting_names - registered}"


def test_mcp_server_registers_accounting():
    """MCP server should register accounting tools."""
    from tools_server import mcp
    # FastMCP exposes registered tools via _tool_manager
    tool_names = set()
    for tool in mcp._tool_manager._tools.values():
        tool_names.add(tool.name)
    assert "fa_ledger" in tool_names
    assert "fa_tx_new" in tool_names
