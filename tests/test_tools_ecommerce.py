"""Test that ecommerce tools are importable."""


def test_ecommerce_tools_registered():
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools.ecommerce  # noqa: F401
    expected = {"ebay_search", "amazon_search", "cl_search", "ec_enrich"}
    assert expected.issubset(set(TOOL_REGISTRY.keys()))


def test_ebay_sort_options():
    from tools.ecommerce import EBAY_SORT_OPTIONS
    assert "best_match" in EBAY_SORT_OPTIONS
    assert "price_low" in EBAY_SORT_OPTIONS


def test_denver_area_cities():
    from tools.ecommerce import CRAIGSLIST_DENVER_AREA
    assert "denver" in CRAIGSLIST_DENVER_AREA
