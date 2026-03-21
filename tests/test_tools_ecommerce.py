"""Test that ecommerce tools are importable."""


def test_ecommerce_tools_importable():
    from tools.ecommerce import ECOMMERCE_TOOLS
    assert len(ECOMMERCE_TOOLS) == 6
    names = {t.name for t in ECOMMERCE_TOOLS}
    expected = {
        "ebay_search", "ebay_sold_search", "ebay_deep_scan",
        "amazon_search", "craigslist_search", "craigslist_multi_search",
    }
    assert names == expected


def test_flow_tools_separate():
    """Flow tools exist but are NOT in ECOMMERCE_TOOLS — they belong to the dispatcher."""
    from tools.ecommerce import FLOW_TOOLS
    assert len(FLOW_TOOLS) == 3
    names = {t.name for t in FLOW_TOOLS}
    assert names == {"cross_platform_search", "deal_finder", "enrichment_pipeline"}


def test_ebay_sort_options():
    from tools.ecommerce import EBAY_SORT_OPTIONS
    assert "best_match" in EBAY_SORT_OPTIONS
    assert "price_low" in EBAY_SORT_OPTIONS


def test_denver_area_cities():
    from tools.ecommerce import CRAIGSLIST_DENVER_AREA
    assert "denver" in CRAIGSLIST_DENVER_AREA
