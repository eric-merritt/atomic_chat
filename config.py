"""Central configuration."""

import os

# Pre-pass model for dynamic tool selection
PREPASS_MODEL = os.environ.get("PREPASS_MODEL", "qwen3:1.7b")

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2
