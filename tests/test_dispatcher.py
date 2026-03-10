"""Test dispatcher agent components."""
import asyncio


def test_dispatcher_importable():
    from agents.dispatcher import create_app
    from mcp.server.fastmcp import FastMCP
    app = create_app()
    assert isinstance(app, FastMCP)
    assert app.name == "dispatcher-agent"


def test_rate_limiter():
    from agents.dispatcher import PlatformRateLimiter
    limiter = PlatformRateLimiter()

    async def check():
        # First call should not wait
        import time
        start = time.monotonic()
        await limiter.acquire("ebay")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # First call is instant

    asyncio.run(check())


def test_classify_platform():
    from agents.dispatcher import classify_platform
    assert classify_platform("ebay_search") == "ebay"
    assert classify_platform("ebay_sold_search") == "ebay"
    assert classify_platform("ebay_deep_scan") == "ebay"
    assert classify_platform("amazon_search") == "amazon"
    assert classify_platform("craigslist_search") == "craigslist"
    assert classify_platform("craigslist_multi_search") == "craigslist"
    assert classify_platform("web_search") == "other"


def test_tool_registry_loaded():
    from agents.dispatcher import TOOL_REGISTRY
    assert len(TOOL_REGISTRY) > 0
    # Check it has tool metadata, not actual tool objects
    first = TOOL_REGISTRY[0]
    assert "name" in first
    assert "description" in first
    assert "params" in first
