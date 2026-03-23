"""Central configuration."""

import os

# Task-aware tool curation models
TASK_EXTRACTOR_MODEL = os.environ.get("TASK_EXTRACTOR_MODEL", "qwen3:1.7b")
TOOL_CURATOR_MODEL = os.environ.get("TOOL_CURATOR_MODEL", "qwen3:1.7b")

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2
