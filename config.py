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
    "filesystem": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "codesearch": "huihui_ai/qwen2.5-coder-abliterate:14b",
    "web": "huihui_ai/qwen2.5-coder-abliterate:14b",
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

# ── LLM context window ───────────────────────────────────────────────────────
# qwen2.5 abliterated variants support up to 128k context
NUM_CTX = 131072  # 128K tokens

# ── ChromaDB / RAG settings ──────────────────────────────────────────────────
CHROMA_DIR = "code_db"
EMBED_MODEL = "nomic-embed-text"

# Chunking — larger chunks preserve more coherent context per retrieval hit.
# With 128K context we can afford to pull bigger, more complete snippets.
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

# Number of documents to retrieve per query
RETRIEVAL_K = 10

# Minimum relevance score (0.0–1.0) to include a chunk.
# Chunks below this threshold are discarded — prevents injecting
# irrelevant context for queries that don't match the codebase
# (e.g. "search for breaking bad torrents").
RETRIEVAL_MIN_SCORE = 0.35

# File extensions to index
INDEX_EXTENSIONS = (".py", ".md", ".txt", ".js", ".ts", ".go", ".rs", ".java", ".cpp")

# Directories to skip during indexing
INDEX_IGNORE_DIRS = {".venv", "__pycache__", ".git", "code_db", "tests", "nginx", "static", "node_modules"}

# Base URL for subagent HTTP calls (from dispatcher)
def agent_url(name: str) -> str:
    """Return the HTTP base URL for a named agent."""
    port = AGENT_PORTS[name]
    return f"http://127.0.0.1:{port}"
