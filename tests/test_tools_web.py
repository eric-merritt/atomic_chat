"""Test that web tools are importable."""


def test_web_tools_importable():
    from tools.web import WEB_TOOLS
    assert len(WEB_TOOLS) == 2
    names = {t.name for t in WEB_TOOLS}
    assert names == {"web_search", "fetch_url"}
