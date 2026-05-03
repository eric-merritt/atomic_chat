"""Central configuration."""

import os

# Default workspace for file operations when no path directory is given
DEFAULT_WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", os.path.expanduser("~/workspace"))

# Context window size (tokens). Subtract a 5000-token safety margin so qwen-agent's
# tool schemas, system prompt, and tool-result fan-in cannot push us past the model
# window mid-turn. Default is conservative; production envs should set explicitly.
def _resolve_ctx_size() -> int:
  raw = os.environ.get("LLAMA_ARG_CTX_SIZE")
  if raw is None or not raw.strip():
    return 32000 - 5000  # safe default for the documented qwen3.5 model set
  try:
    parsed = int(raw)
  except (TypeError, ValueError) as parse_err:
    raise RuntimeError(
      f"LLAMA_ARG_CTX_SIZE must be an integer (got {raw!r}): {parse_err}"
    ) from parse_err
  if parsed <= 5000:
    raise RuntimeError(
      f"LLAMA_ARG_CTX_SIZE={parsed} is too small. Must exceed the 5000-token safety margin."
    )
  return parsed - 5000

LLAMA_ARG_CTX_SIZE = _resolve_ctx_size()

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

import re as _re
_params_match = _re.search(r'(\d+b)', DEFAULT_MODEL.lower())
MODEL_NUM_PARAMS = _params_match.group(1) if _params_match else 'unknown'

SAVE_DIR = os.environ.get(
    "SAVE_DIR",
    os.path.expanduser(f"~/.atomic_chat/agent_downloads/{MODEL_NUM_PARAMS}")
)

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


# ── Bridge RSA key pair ──────────────────────────────────────────────────────
import pathlib as _pathlib

_KEYS_DIR = _pathlib.Path(__file__).parent / "keys"


def _load_or_generate_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _KEYS_DIR.mkdir(mode=0o700, exist_ok=True)
    priv_path = _KEYS_DIR / "server_private.pem"

    if priv_path.exists():
        private_key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_path.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
        priv_path.chmod(0o600)

    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, public_pem


SERVER_PRIVATE_KEY, SERVER_PUBLIC_KEY_PEM = _load_or_generate_keypair()


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
