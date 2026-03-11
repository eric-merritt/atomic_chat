"""Integration test — verifies the full agent stack.

Requires agents to be running. Skip if not available.
Run with: python run_agents.py & pytest tests/test_integration.py -v
"""
import asyncio
import os
import tempfile

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def agent_available(port: int) -> bool:
    """Check if an MCP agent is responding on the given port."""
    async def check():
        try:
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                read_stream, write_stream, _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return True
        except Exception:
            return False
    return asyncio.run(check())


@pytest.fixture(autouse=True)
def skip_if_no_agents():
    if not agent_available(8101):
        pytest.skip("Agents not running — start with: python run_agents.py")


def test_filesystem_agent_lists_tools():
    async def run():
        async with streamable_http_client("http://127.0.0.1:8101/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "read_file" in names
                assert "write_file" in names
    asyncio.run(run())


def test_filesystem_agent_read_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content\n")
        path = f.name
    try:
        async def run():
            async with streamable_http_client("http://127.0.0.1:8101/mcp") as (
                read_stream, write_stream, _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool("read_file", arguments={"path": path})
                    text = result.content[0].text
                    assert "test content" in text
        asyncio.run(run())
    finally:
        os.unlink(path)


def test_dispatcher_lists_tools():
    if not agent_available(8105):
        pytest.skip("Dispatcher not running")

    async def run():
        async with streamable_http_client("http://127.0.0.1:8105/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "dispatch" in names
                assert "dispatch_parallel" in names
                assert "check_quality" in names
    asyncio.run(run())
