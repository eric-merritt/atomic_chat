"""Test that web tools are importable."""


def test_web_tools_importable():
    from tools.web import WEB_TOOLS
    assert len(WEB_TOOLS) == 7
    names = {t.name for t in WEB_TOOLS}
    assert {"web_search", "fetch_url"}.issubset(names)
