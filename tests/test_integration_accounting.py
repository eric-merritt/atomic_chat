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
    from tools.accounting import ACCOUNTING_TOOLS
    assert len(ACCOUNTING_TOOLS) == 21


def test_mcp_server_registers_accounting():
    """MCP server should register accounting tools."""
    from tools_server import mcp
    # FastMCP exposes registered tools via _tool_manager
    tool_names = set()
    for tool in mcp._tool_manager._tools.values():
        tool_names.add(tool.name)
    assert "create_ledger" in tool_names
    assert "journalize_transaction" in tool_names
