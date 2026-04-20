"""Central configuration."""

import os

# Default workspace for file operations when no path directory is given
DEFAULT_WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", os.path.expanduser("~/workspace"))

# Context window size (tokens)
LLAMA_ARG_CTX_SIZE = int(os.environ.get("LLAMA_ARG_CTX_SIZE", "32768"))

# Seconds between requests to the same platform
RATE_LIMITS = {
  "ebay": 6,
  "amazon": 6,
  "craigslist": 6,
  "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2


SUMMARIZE_MODEL = os.environ.get("SUMMARIZE_MODEL", "qwen2.5:1.5b")
CONTEXT_SUMMARIZE_THRESHOLD = float(os.environ.get("CONTEXT_SUMMARIZE_THRESHOLD", "0.75"))


def qwen_llm_cfg(model: str = "", num_ctx: int = 0) -> dict:
  """Build a qwen-agent LLM config pointing at the local llama.cpp server."""
  return {
  'model': model or os.environ.get('CHAT_MODEL', 'qwen3:8b'),
  'model_type': 'oai',
  'model_server': os.environ.get('LLAMA_CPP_BASE_URL', 'http://localhost:8080') + '/v1',
  'api_key': 'EMPTY',
  'generate_cfg': {
    'max_input_tokens': num_ctx or LLAMA_ARG_CTX_SIZE,
  },
  }


