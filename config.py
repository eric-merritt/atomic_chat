"""Central configuration."""

import os

# Default workspace for file operations when no path directory is given
DEFAULT_WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", os.path.expanduser("~/workspace"))

# Task-aware tool curation models
TASK_EXTRACTOR_MODEL = os.environ.get("TASK_EXTRACTOR_MODEL", "qwen3:1.7b")
TOOL_CURATOR_MODEL = os.environ.get("TOOL_CURATOR_MODEL", "qwen3:1.7b")

# Context window sizes (tokens) — set to each model's max
# qwen3:1.7b max=32768, qwen3:8b max=128k (use 32k default for VRAM)
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "32768"))
OLLAMA_CURATION_NUM_CTX = int(os.environ.get("OLLAMA_CURATION_NUM_CTX", "32768"))

# Seconds between requests to the same platform
RATE_LIMITS = {
    "ebay": 6,
    "amazon": 6,
    "craigslist": 6,
    "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2
