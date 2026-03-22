"""Integration test: pre-pass fallback when tool index isn't loaded."""

def test_select_tools_fallback_without_index():
    """select_tools returns fallback when index hasn't been loaded."""
    from prepass import select_tools

    fallback = ["read", "ls", "write"]
    result = select_tools("do something", fallback)
    assert result == fallback
