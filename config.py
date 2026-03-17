"""Central configuration for all agents."""

# Port assignments per agent
AGENT_PORTS = {
    "filesystem": 8101,
    "codesearch": 8102,
    "web": 8103,
    "marketplace": 8104,
    "dispatcher": 8105,
}

# Ollama model per agent — override with env vars or CLI args
AGENT_MODELS = {
    "filesystem": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "codesearch": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "web": "huihui_ai/qwen2.5-coder-abliterate:7b",
    "marketplace": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "dispatcher": "huihui_ai/qwen2.5-coder-abliterate:14b",
}

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2

# Base URL for subagent HTTP calls (from dispatcher)
def agent_url(name: str) -> str:
    """Return the HTTP base URL for a named agent."""
    port = AGENT_PORTS[name]
    return f"http://127.0.0.1:{port}"
