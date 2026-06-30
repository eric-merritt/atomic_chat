"""Central configuration."""

import os

# Default workspace for file operations when no path directory is given
DEFAULT_WORKSPACE = os.environ.get(
    "DEFAULT_WORKSPACE", os.path.expanduser("~/workspace")
)


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

# The summary server runs a smaller window than the main model (SUMMARY_CTX /
# config.SUMMARY_LLAMA). Budget the summary agent against ITS window, not the main one, or
# qwen-agent sends oversized prompts and the summary server 400s on overflow.
# ── llama-server process ──
# The binary actually serving in production is /usr/local/bin/llama-server.
# A newer build also exists at ~/models/llama.cpp/build/bin/llama-server —
# override via LLAMA_BIN to switch to it.
LLAMA_BIN = os.environ.get(
    "LLAMA_BIN", "/home/ermer/models/llama.cpp/build/bin/llama-server"
)
LLAMA_HOST = os.environ.get("LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "7368"))
LLAMA_SERVER_URL = os.environ.get(
    "LLAMA_SERVER_URL", f"http://{LLAMA_HOST}:{LLAMA_PORT}"
)

# ── Model registry ──
# alias (shown to UI, used as --alias and as /v1/chat/completions `model` field)
# → GGUF file on disk + launch args.
MODELS = {
    "qwen3.6:27b-iq4_xs": {
        "path": "$QWEN_LATEST",
        "ngl": 44,
        "ctx": 24000,
    },
    "qwen3.5:27b-iq4_xs": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-27B/Qwen3.5-27B-IQ4_XS.gguf",
        "ngl": 44,
        "ctx": 32000,
    },
    "qwen3.5:9b-iq4_xs": {
        "path": "/home/ermer/models/Qwen/Qwen3.5-9B-Ablit/Qwen3.5-9B-Ablit-IQ4_XS.gguf",
        "ngl": "auto",
        "ctx": 16000,
    },
}

DEFAULT_MODEL = os.environ["DEFAULT_MODEL"]

# Tool router backend: "toolsdb" (codebase-memory-mcp SQLite graph, FTS5 +
# graphify summaries) or "neo4j" (graphify graph via Neo4j, keyword fulltext).
# Default is toolsdb; set TOOL_ROUTER=neo4j to fall back to the Neo4j island.
TOOL_ROUTER = os.environ.get("TOOL_ROUTER", "toolsdb")

import re as _re

_params_match = _re.search(r"(\d+b)", DEFAULT_MODEL.lower())
MODEL_NUM_PARAMS = _params_match.group(1) if _params_match else "unknown"

SAVE_DIR = os.environ.get(
    "SAVE_DIR", os.path.expanduser(f"~/.atomic_chat/agent_downloads/{MODEL_NUM_PARAMS}")
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


SUMMARIZE_MODEL = os.environ["SUMMARIZE_MODEL"]
CONTEXT_SUMMARIZE_THRESHOLD = float(
    os.environ.get("CONTEXT_SUMMARIZE_THRESHOLD", "0.75")
)


# ── Service ports ──
# Single source of truth shared by launch.py and each service. FRONTEND_PORT
# must match frontend/vite.config.ts (Vite owns its own port at runtime).
TOOLS_PORT = int(os.environ.get("TOOLS_PORT", "8463"))
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8297"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "6612"))


# ── llama-server launch specs ──
# How launch.py starts each llama-server via the compiled binary. Every value is
# env-overridable. Defaults mirror the production cmdline exactly. The MODELS
# registry above is a separate concern (runtime catalog / token budgeting).
MMPROJ_PATH = os.environ.get(
    "MMPROJ",
    "/home/ermer/models/Qwen/Qwen3.6-27B-Ablit/gguf_quants/mmproj-BF16.gguf",
)

MAIN_LLAMA = {
    "name": "llama",
    "bin": LLAMA_BIN,
    "model": os.environ.get("MODEL") or os.environ.get("QWEN_LATEST"),
    "alias": os.environ.get("MODEL_ALIAS", SUMMARIZE_MODEL),
    "host": "0.0.0.0",
    "port": LLAMA_PORT,
    "ngl": int(os.environ.get("MODEL_NGL", "44")),
    "ctx": int(os.environ.get("MODEL_CTX", "24000")),
    "parallel": int(os.environ.get("MODEL_PARALLEL", "2")),
    "flash_attn": True,
    "cache_type": "q8_0",
    "mmproj": None,
    "spec_type": "draft-mtp",
    "spec_draft_n_max": 2,
    "spec_draft_p_min": 0.85,
}


# ── Bridge RSA key pair ──────────────────────────────────────────────────────
import pathlib as _pathlib

_KEYS_DIR = _pathlib.Path(__file__).parent / "keys"


def _load_or_generate_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _KEYS_DIR.mkdir(mode=0o700, exist_ok=True)
    priv_path = _KEYS_DIR / "server_private.pem"

    if priv_path.exists():
        private_key = serialization.load_pem_private_key(
            priv_path.read_bytes(), password=None
        )
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_path.write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        priv_path.chmod(0o600)

    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_key, public_pem


SERVER_PRIVATE_KEY, SERVER_PUBLIC_KEY_PEM = _load_or_generate_keypair()


def qwen_llm_cfg(model: str = "", num_ctx: int = 0) -> dict:
    """Build a qwen-agent LLM config pointing at the local llama.cpp instance."""
    return {
        "model": model or DEFAULT_MODEL,
        "model_type": "oai",
        "model_server": LLAMA_SERVER_URL + "/v1",
        "api_key": "EMPTY",
        "generate_cfg": {
            "max_input_tokens": num_ctx or LLAMA_ARG_CTX_SIZE,
            "extra_body": {"id_slot": 0},
        },
    }


def qwen_summary_cfg(num_ctx: int = 0) -> dict:
    """Build a qwen-agent LLM config pointing at the summary slot of the main instance."""
    return {
        "model": SUMMARIZE_MODEL,
        "model_type": "oai",
        "model_server": LLAMA_SERVER_URL + "/v1",
        "api_key": "EMPTY",
        "generate_cfg": {
            "max_input_tokens": num_ctx or LLAMA_ARG_CTX_SIZE,
            "extra_body": {"id_slot": 1, "cache_prompt": False},
        },
    }
