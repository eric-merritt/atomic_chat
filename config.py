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


def qwen_llm_cfg(model: str = "", num_ctx: int = 0) -> dict:
    """Build a qwen-agent LLM config pointing at the local Ollama instance."""
    return {
        'model': model or os.environ.get('CHAT_MODEL', 'qwen3:8b'),
        'model_type': 'oai',
        'model_server': os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434') + '/v1',
        'api_key': 'EMPTY',
        'generate_cfg': {
            'max_input_tokens': num_ctx or OLLAMA_NUM_CTX,
        },
    }


def qwen_curation_llm_cfg(model: str = "") -> dict:
    """Build a qwen-agent LLM config for 1.7B curation workers."""
    return {
        'model': model or TASK_EXTRACTOR_MODEL,
        'model_type': 'oai',
        'model_server': os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434') + '/v1',
        'api_key': 'EMPTY',
        'generate_cfg': {
            'max_input_tokens': OLLAMA_CURATION_NUM_CTX,
        },
    }
