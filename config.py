"""Central configuration."""

import os

# Default workspace for file operations when no path directory is given
DEFAULT_WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", os.path.expanduser("~/workspace"))

# Context window size (tokens)
LLAMA_ARG_CTX_SIZE = int(os.environ.get("LLAMA_ARG_CTX_SIZE")) - 5000

# ── llama-server process ──
LLAMA_HOST = os.environ.get("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "5173"))
LLAMA_SERVER_URL = os.environ.get(
    "LLAMA_SERVER_URL", f"http://{LLAMA_HOST}:{LLAMA_PORT}"
)

# ── Model registry ──
# alias (shown to UI, used as --alias and as /v1/chat/completions `model` field)
# → GGUF file on disk + launch args.
MODELS = {
    "qwen3.5:27b-iq4_xs": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-27B/Qwen3.5-27B-IQ4_XS.gguf",
        "ngl": 44,
        "ctx": 32000,
    },
    "qwen3.5:27b-q4km": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-27B/Qwen3.5-27B-Q4_K_M.gguf",
        "ngl": 64,
        "ctx": 32000,
    },
    "qwen3.5:9b-q8": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-9B/Qwen3.5-9B-Q8_0.gguf",
        "ngl": 99,
        "ctx": 64000,
    },
    "qwen3.5:9b-q4km": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-9B/Qwen3.5-9B-Q4_K_M.gguf",
        "ngl": 99,
        "ctx": 100000,
    },
    "qwen3.5:9b-q4ks": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-9B/Qwen3.5-9B-Q4_K_S.gguf",
        "ngl": 99,
        "ctx": 100000
    }
}

DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "qwen3.5:27b-iq4_xs")

# Seconds between requests to the same platform
RATE_LIMITS = {
  "ebay": 6,
  "amazon": 6,
  "craigslist": 6,
  "default": 6,
}

# Dispatcher retry config
MAX_RETRIES = 2


LLAMA_SUMMARY_PORT = int(os.environ.get("LLAMA_SUMMARY_PORT", "5175"))
SUMMARIZE_MODEL = os.environ.get("SUMMARIZE_MODEL", "qwen3.5:4b-q5_k_m")
SUMMARIZE_SERVER_URL = os.environ.get(
    "SUMMARIZE_SERVER_URL", f"http://{LLAMA_HOST}:{LLAMA_SUMMARY_PORT}"
)
CONTEXT_SUMMARIZE_THRESHOLD = float(os.environ.get("CONTEXT_SUMMARIZE_THRESHOLD", "0.75"))


def qwen_llm_cfg(model: str = "", num_ctx: int = 0) -> dict:
  """Build a qwen-agent LLM config pointing at the local llama.cpp instance."""
  return {
  'model': model or DEFAULT_MODEL,
  'model_type': 'oai',
  'model_server': LLAMA_SERVER_URL + '/v1',
  'api_key': 'EMPTY',
  'generate_cfg': {
    'max_input_tokens': num_ctx or LLAMA_ARG_CTX_SIZE,
  },
  }
