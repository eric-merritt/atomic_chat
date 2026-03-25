"""Test that ecommerce tools are importable."""


def test_ecommerce_tools_registered():
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools.ecommerce  # noqa: F401
    expected = {
        "ebay_search", "ebay_sold_search", "ebay_deep_scan",
        "amazon_search", "craigslist_search", "craigslist_multi_search",
    }
    assert expected.issubset(set(TOOL_REGISTRY.keys()))


def test_flow_tools_registered():
    from qwen_agent.tools.base import TOOL_REGISTRY
    import tools.ecommerce  # noqa: F401
    expected = {"cross_platform_search", "deal_finder", "enrichment_pipeline"}
    assert expected.issubset(set(TOOL_REGISTRY.keys()))


def test_ebay_sort_options():
    from tools.ecommerce import EBAY_SORT_OPTIONS
    assert "best_match" in EBAY_SORT_OPTIONS
    assert "price_low" in EBAY_SORT_OPTIONS


def test_denver_area_cities():
    from tools.ecommerce import CRAIGSLIST_DENVER_AREA
    assert "denver" in CRAIGSLIST_DENVER_AREA
