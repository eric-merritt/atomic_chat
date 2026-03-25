# tests/test_integration_accounting.py
"""Test accounting tools are registered and accessible."""


def test_accounting_tools_in_registry():
    from tools import ALL_TOOLS
    names = {t.name for t in ALL_TOOLS}
    assert "create_ledger" in names
    assert "journalize_transaction" in names
    assert "trial_balance" in names
    assert "balance_sheet" in names


def test_accounting_tool_count():
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools.accounting  # noqa: F401
    accounting_names = {
        'create_ledger', 'create_account', 'list_accounts', 'get_account_balance',
        'update_account', 'journalize_transaction', 'search_journal', 'void_transaction',
        'account_ledger', 'register_inventory_item', 'receive_inventory',
        'list_inventory_items', 'deactivate_inventory_item', 'journalize_fifo_transaction',
        'journalize_lifo_transaction', 'inventory_valuation', 'close_period',
        'trial_balance', 'income_statement', 'balance_sheet', 'cash_flow_statement',
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
    assert "create_ledger" in tool_names
    assert "journalize_transaction" in tool_names
