"""Dispatcher/analyst agent — orchestrates subagents and does all reasoning.

Port: 8105
Tools: None directly (has tool definitions for planning)
Model: strongest available abliterated model

The dispatcher:
1. Receives user requests via MCP
2. Plans which subagents to call with what parameters
3. Fans out requests (parallel across platforms, sequential within)
4. Evaluates result quality via LLM self-eval
5. Retries on bad data (max 2 retries)
6. Analyzes, deduplicates, ranks, presents results
"""

import asyncio
import json
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

from config import AGENT_PORTS, RATE_LIMITS, MAX_RETRIES, agent_url, AGENT_MODELS
from tools.filesystem import FILESYSTEM_TOOLS
from tools.codesearch import CODESEARCH_TOOLS
from tools.web import WEB_TOOLS
from tools.marketplace import MARKETPLACE_TOOLS


# ── Tool registry (metadata only, for planning) ──────────────────────────────

def _tool_meta(t) -> dict:
    """Extract name, description, and parameter info from a LangChain tool."""
    schema = t.args_schema.model_json_schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            params[pname]["default"] = pinfo["default"]
    return {
        "name": t.name,
        "description": t.description.split("\n")[0] if t.description else "",
        "params": params,
    }


# Map tool names to which agent owns them
TOOL_TO_AGENT = {}
for t in FILESYSTEM_TOOLS:
    TOOL_TO_AGENT[t.name] = "filesystem"
for t in CODESEARCH_TOOLS:
    TOOL_TO_AGENT[t.name] = "codesearch"
for t in WEB_TOOLS:
    TOOL_TO_AGENT[t.name] = "web"
for t in MARKETPLACE_TOOLS:
    TOOL_TO_AGENT[t.name] = "marketplace"

ALL_AGENT_TOOLS = FILESYSTEM_TOOLS + CODESEARCH_TOOLS + WEB_TOOLS + MARKETPLACE_TOOLS
TOOL_REGISTRY = [_tool_meta(t) for t in ALL_AGENT_TOOLS]


# ── Platform classification ──────────────────────────────────────────────────

def classify_platform(tool_name: str) -> str:
    """Classify a tool name into its rate-limit platform group."""
    if tool_name.startswith("ebay"):
        return "ebay"
    if tool_name.startswith("amazon"):
        return "amazon"
    if tool_name.startswith("craigslist"):
        return "craigslist"
    return "other"


# ── Rate limiter ─────────────────────────────────────────────────────────────

class PlatformRateLimiter:
    """Enforces per-platform cooldowns between requests."""

    def __init__(self):
        self._last_call: dict[str, float] = {}
        # Pre-initialize all known platform locks to avoid race conditions
        self._locks: dict[str, asyncio.Lock] = {
            "ebay": asyncio.Lock(),
            "amazon": asyncio.Lock(),
            "craigslist": asyncio.Lock(),
            "other": asyncio.Lock(),
        }

    def _get_lock(self, platform: str) -> asyncio.Lock:
        if platform not in self._locks:
            self._locks[platform] = asyncio.Lock()
        return self._locks[platform]

    async def acquire(self, platform: str) -> None:
        """Wait until the cooldown for this platform has elapsed."""
        lock = self._get_lock(platform)
        async with lock:
            cooldown = RATE_LIMITS.get(platform, RATE_LIMITS["default"])
            last = self._last_call.get(platform, 0)
            elapsed = time.monotonic() - last
            if elapsed < cooldown:
                await asyncio.sleep(cooldown - elapsed)
            self._last_call[platform] = time.monotonic()


# ── Subagent MCP client ──────────────────────────────────────────────────────

async def call_subagent(
    agent_name: str,
    tool_name: str,
    params: dict,
    rate_limiter: PlatformRateLimiter,
) -> dict:
    """Call a subagent's tool via the MCP client library.

    Uses streamable_http_client to connect to the subagent's MCP server
    and call tools through the proper MCP protocol.

    Args:
        agent_name: Name of the agent (e.g., "marketplace")
        tool_name: Name of the tool to invoke
        params: Tool parameters

    Returns:
        {"status": "ok", "data": ..., "tool": tool_name} or
        {"status": "error", "error": ..., "tool": tool_name}
    """
    platform = classify_platform(tool_name)
    if platform != "other":
        await rate_limiter.acquire(platform)

    base_url = agent_url(agent_name)
    try:
        async with streamable_http_client(f"{base_url}/mcp") as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=params)

                # Extract text content from MCP result
                data = ""
                for item in result.content:
                    if item.type == "text":
                        data = item.text
                        break

                return {"status": "ok", "data": data, "tool": tool_name}

    except Exception as e:
        return {"status": "error", "error": str(e), "tool": tool_name}


# ── Dispatcher system prompt ─────────────────────────────────────────────────

DISPATCHER_SYSTEM_PROMPT = """You are a dispatcher/analyst agent. You orchestrate specialized subagents to gather data, then analyze and present results.

## Your role
- You have knowledge of all available tools across all agents (see TOOL_REGISTRY below).
- Plan which agents to call with what parameters.
- When results come back, evaluate quality.
- When presenting final results to the user, extract and present the actual data.

## Rules
- Never describe data formats. Never speculate about intent.
- Never ask clarifying questions you can resolve yourself.
- Do not summarize tool results — extract the actual data and present it.
- If given data to analyze, analyze it. If given data to search, search it.
- If results are empty or garbage, say so in one sentence.

## Available tools (for planning — you delegate execution):
{tool_list}

## Marketplace tool selection
- ebay_search: Quick single-page eBay lookup
- ebay_sold_search: eBay completed/sold listings for market prices
- ebay_deep_scan: Multi-page paginated eBay scan with GPU model extraction
- amazon_search: Search Amazon product listings
- craigslist_search: Search one Craigslist city
- craigslist_multi_search: Search multiple Craigslist cities

## Rate limiting
- Requests to the same platform (eBay, Amazon, Craigslist) are sequential with cooldowns.
- Requests to different platforms run in parallel.

## GPU generations reference
Only consider Turing (2018) or newer for AI/ML relevance:
- Turing: RTX 2060/2070/2080, GTX 1650/1660, T4
- Ampere: RTX 3060/3070/3080/3090, A100/A40/A6000
- Ada Lovelace: RTX 4060/4070/4080/4090, L40/L40S
- Hopper: H100, H200
- Blackwell: RTX 5070/5080/5090, B100/B200/GB200

## eBay price analysis rules
1. Group by exact GPU model
2. Compute per-group median (not mean)
3. Flag as underpriced only if >=20% below median AND group has >=3 listings
4. Always add shipping to price before comparing
5. Show: model, total price, group median, % below median, URL
6. If no deals found, say so explicitly

## Craigslist fulfillment
- Denver area (pickup OK): denver, boulder, colorado springs, fort collins, pueblo
- All other cities: shipping required
"""


# ── MCP server creation ──────────────────────────────────────────────────────

def create_app():
    # Format tool list for the system prompt
    tool_list = "\n".join(
        f"- {t['name']}: {t['description']}"
        for t in TOOL_REGISTRY
    )
    prompt = DISPATCHER_SYSTEM_PROMPT.format(tool_list=tool_list)

    mcp = FastMCP(
        "dispatcher-agent",
        stateless_http=True,
        json_response=True,
    )

    rate_limiter = PlatformRateLimiter()

    @mcp.tool()
    async def dispatch(
        tool_name: str,
        params: str = "{}",
    ) -> str:
        """Call a subagent tool by name with JSON params.

        Args:
            tool_name: Name of the tool to invoke (e.g., "ebay_search")
            params: JSON string of tool parameters
        """
        if tool_name not in TOOL_TO_AGENT:
            return json.dumps({"status": "error", "error": f"Unknown tool: {tool_name}"})

        agent_name = TOOL_TO_AGENT[tool_name]
        try:
            parsed_params = json.loads(params) if isinstance(params, str) else params
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"Invalid params JSON: {e}"})

        result = await call_subagent(agent_name, tool_name, parsed_params, rate_limiter)
        return json.dumps(result)

    @mcp.tool()
    async def dispatch_parallel(
        requests: str,
    ) -> str:
        """Call multiple subagent tools in parallel (respecting rate limits).

        Args:
            requests: JSON array of {"tool": "name", "params": {...}} objects.
                      Tools on different platforms run in parallel.
                      Tools on the same platform run sequentially with cooldown.
        """
        try:
            req_list = json.loads(requests)
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "error": f"Invalid JSON: {e}"})

        # Group by platform for parallel execution
        platform_groups: dict[str, list] = {}
        for req in req_list:
            tool_name = req.get("tool", "")
            platform = classify_platform(tool_name)
            platform_groups.setdefault(platform, []).append(req)

        async def run_platform_group(reqs):
            """Run a group of same-platform requests sequentially."""
            results = []
            for req in reqs:
                tool_name = req.get("tool", "")
                params = req.get("params", {})
                agent_name = TOOL_TO_AGENT.get(tool_name)
                if not agent_name:
                    results.append({"status": "error", "error": f"Unknown tool: {tool_name}", "tool": tool_name})
                    continue
                result = await call_subagent(agent_name, tool_name, params, rate_limiter)
                results.append(result)
            return results

        # Run all platform groups in parallel
        tasks = [run_platform_group(reqs) for reqs in platform_groups.values()]
        group_results = await asyncio.gather(*tasks)

        # Flatten results
        all_results = []
        for group in group_results:
            all_results.extend(group)

        return json.dumps(all_results)

    @mcp.tool()
    async def check_quality(
        data: str,
        expected_format: str = "marketplace_listings",
    ) -> str:
        """Evaluate the quality of data returned by a subagent.

        Uses LLM self-eval to determine if the data is valid or garbage.

        Args:
            data: The data string to evaluate
            expected_format: What kind of data this should be
                           (e.g., "marketplace_listings", "file_contents", "search_results")
        """
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage

        model = AGENT_MODELS.get("dispatcher", "huihui_ai/qwen2.5-coder-abliterate:14b")
        llm = ChatOllama(model=model, temperature=0, base_url="http://localhost:11434")

        eval_prompt = f"""Evaluate this data. Expected format: {expected_format}.

Is this valid, usable data? Reply with ONLY a JSON object:
{{"valid": true/false, "reason": "brief explanation", "suggestion": "how to fix if invalid"}}

Data to evaluate:
{data[:2000]}"""

        result = llm.invoke([
            SystemMessage(content="You are a data quality evaluator. Return ONLY valid JSON. No other text."),
            HumanMessage(content=eval_prompt),
        ])
        return result.content

    return mcp


if __name__ == "__main__":
    app = create_app()
    app.run(transport="streamable-http", port=AGENT_PORTS["dispatcher"])
