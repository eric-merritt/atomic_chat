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


def test_tools_server_lists_accounting():
    """tools_server.py Flask app should list accounting tools."""
    from tools_server import tools_app
    client = tools_app.test_client()
    resp = client.get("/")
    data = resp.get_json()
    assert "create_ledger" in data
    assert "journalize_transaction" in data
