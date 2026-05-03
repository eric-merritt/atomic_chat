#!/usr/bin/env bash
# install.sh — Atomic Chat Installer
#
# Path 1: Full Local Stack  — self-hosted LLM + backend + frontend, no cloud
#                             After install: ./start.sh
# Path 2: Cloud Client Only — agent bridge to agent.eric-merritt.com
#                             After install: ./agent

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()  { printf "${GREEN}[+]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[!]${RESET} %s\n" "$*"; }
error() { printf "${RED}[x]${RESET} %s\n" "$*" >&2; exit 1; }
step()  { printf "\n${CYAN}${BOLD}▶ %s${RESET}\n" "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

printf "${BOLD}╔══════════════════════════════════╗${RESET}\n"
printf "${BOLD}║     Atomic Chat  —  Installer    ║${RESET}\n"
printf "${BOLD}╚══════════════════════════════════╝${RESET}\n\n"

printf "${BOLD}Choose installation type:${RESET}\n"
printf "  [1] Full Local Stack    — self-hosted LLM + backend + frontend, no cloud\n"
printf "  [2] Cloud Client Only   — connect your machine to agent.eric-merritt.com\n\n"
printf "Choice [1/2]: "; read -r PATH_CHOICE
case "$PATH_CHOICE" in
    1) INSTALL_PATH="local" ;;
    2) INSTALL_PATH="cloud" ;;
    *) error "Enter 1 or 2." ;;
esac

# ── Python ────────────────────────────────────────────────────────────────────
step "Checking Python..."
PYTHON=""
for _cmd in python3.12 python3.13 python3; do
    if command -v "$_cmd" &>/dev/null; then
        _ver=$("$_cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        _major="${_ver%%.*}"; _minor="${_ver##*.}"
        if [[ "$_major" -ge 3 && "$_minor" -ge 12 ]]; then PYTHON="$_cmd"; break; fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    warn "Python >= 3.12 not found."
    printf "Install Python 3.12? [Y/N]: "; read -r _ans
    [[ "$_ans" =~ ^[Yy] ]] || error "Python >= 3.12 required."
    if [[ "$(uname)" == "Darwin" ]]; then
        command -v brew &>/dev/null || error "Homebrew not found. Install: https://brew.sh"
        brew install python@3.12
        PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y python3.12 python3.12-venv
        PYTHON="python3.12"
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3.12; PYTHON="python3.12"
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python; PYTHON="python3"
    else
        error "Install Python 3.12 manually: https://www.python.org/downloads/"
    fi
fi
info "Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ── Shared helpers ────────────────────────────────────────────────────────────
find_free_port() {
    local _start=$1 _end=$2
    "$PYTHON" -c "
import socket, sys
for p in range($_start, $_end + 1):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind(('', p)); print(p); sys.exit(0)
        except OSError: pass
sys.exit(1)
" || error "No free port found in range $_start-$_end"
}

scan_models() {
    "$PYTHON" -c "
from pathlib import Path
for d in [
    Path.home()/'models',
    Path.home()/'.cache/llama.cpp',
    Path.home()/'.cache/huggingface/hub',
    Path.home()/'.ollama/models',
    Path('/opt/models'),
    Path('/usr/local/share/models'),
]:
    if d.exists():
        for p in sorted(d.rglob('*.gguf')): print(p)
"
}

detect_gpu() {
    if [[ "$(uname)" == "Darwin" ]]; then echo "metal"; return; fi
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null 2>&1; then echo "cuda"; return; fi
    if command -v rocminfo &>/dev/null && rocminfo &>/dev/null 2>&1; then echo "rocm"; return; fi
    # Intel Arc (and other Vulkan-capable GPUs without CUDA/ROCm)
    if command -v lspci &>/dev/null && lspci 2>/dev/null | grep -qi "intel.*arc\|intel.*graphics\|alchemist"; then
        echo "vulkan"; return
    fi
    echo "cpu"
}

# ══════════════════════════════════════════════════════════════════════════════
# PATH 1 — FULL LOCAL STACK
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$INSTALL_PATH" == "local" ]]; then

# ── llama-server ──────────────────────────────────────────────────────────────
step "Setting up llama-server..."

LLAMA_BIN=""
for _cand in llama-server "$HOME/.local/bin/llama-server" llama.cpp/build/bin/llama-server; do
    if command -v "$_cand" &>/dev/null 2>&1 || [[ -x "$_cand" ]]; then
        LLAMA_BIN="$(command -v "$_cand" 2>/dev/null || echo "$_cand")"; break
    fi
done

_download_github_release() {
    GPU_BACKEND="$(detect_gpu)"
    EXTRACT_DIR="$SCRIPT_DIR/.llama-cpp"
    "$PYTHON" - "$GPU_BACKEND" "$EXTRACT_DIR" <<'PYEOF'
import urllib.request, json, sys, zipfile, os, stat
from pathlib import Path

gpu     = sys.argv[1]
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

api_url = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
hdrs    = {"User-Agent": "atomic-chat-installer", "Accept": "application/vnd.github+json"}
with urllib.request.urlopen(urllib.request.Request(api_url, headers=hdrs), timeout=20) as r:
    release = json.load(r)

assets = release.get("assets", [])
tag    = release.get("tag_name", "")

# priority-ordered asset name patterns per GPU backend
# ROCm and Vulkan both target the Vulkan build; no Linux ROCm binary in releases
patterns = {
    "cuda":   ["ubuntu-cuda", "linux-cuda"],
    "rocm":   ["ubuntu-vulkan", "linux-vulkan"],
    "vulkan": ["ubuntu-vulkan", "linux-vulkan"],
    "metal":  ["macos", "osx"],
}
fallback = ["ubuntu-x64", "linux-x64", "ubuntu-avx2", "linux-avx2"]

candidates = patterns.get(gpu, []) + fallback
asset = None
for pat in candidates:
    for a in assets:
        name = a["name"].lower()
        if pat in name and name.endswith(".zip"):
            asset = a
            break
    if asset:
        break

if not asset:
    print(f"ERROR: no matching Linux release found for tag {tag}", file=sys.stderr)
    print("Check https://github.com/ggerganov/llama.cpp/releases manually.", file=sys.stderr)
    sys.exit(1)

zip_path = out_dir / asset["name"]
print(f"Downloading {asset['name']} ({asset['size'] >> 20} MB)...", file=sys.stderr)
with urllib.request.urlopen(asset["browser_download_url"], timeout=300) as r, \
        open(zip_path, "wb") as f:
    total = int(r.headers.get("Content-Length", 0))
    done  = 0
    while True:
        chunk = r.read(65536)
        if not chunk: break
        f.write(chunk); done += len(chunk)
        if total:
            pct = min(100, done * 100 // total)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct}%  ", end="", flush=True, file=sys.stderr)
print(file=sys.stderr)

with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(out_dir)
zip_path.unlink()

for p in sorted(out_dir.rglob("llama-server")):
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(str(p))
    sys.exit(0)

print("ERROR: llama-server not found in downloaded archive.", file=sys.stderr)
sys.exit(1)
PYEOF
}

_build_from_source() {
    GPU_BACKEND="$(detect_gpu)"
    case "$GPU_BACKEND" in
        cuda)  CMAKE_FLAGS="-DGGML_CUDA=ON";    info "NVIDIA GPU → CUDA build" ;;
        rocm)  CMAKE_FLAGS="-DGGML_HIPBLAS=ON"; info "AMD ROCm  → HIP build" ;;
        metal) CMAKE_FLAGS="-DGGML_METAL=ON";   info "Apple Silicon → Metal build" ;;
        *)     CMAKE_FLAGS="-DGGML_CUDA=OFF -DGGML_METAL=OFF"; info "CPU-only build (AVX2)" ;;
    esac
    BUILD_DIR="$SCRIPT_DIR/.llama-cpp-build"
    if [[ -d "$BUILD_DIR" ]]; then
        warn "Reusing existing build dir: $BUILD_DIR"
    else
        git clone --depth 1 https://github.com/ggerganov/llama.cpp "$BUILD_DIR"
    fi
    cd "$BUILD_DIR"
    # shellcheck disable=SC2086
    cmake -B build -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release \
        $CMAKE_FLAGS 2>&1 | tail -5
    cmake --build build --config Release \
        -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
    LLAMA_BIN="$BUILD_DIR/build/bin/llama-server"
    cd "$SCRIPT_DIR"
}

if [[ -z "$LLAMA_BIN" ]]; then
    warn "llama-server not found."
    printf "\n  [a] Homebrew (macOS)\n  [b] Download pre-built release from GitHub (ggerganov/llama.cpp)\n  [c] Build from source\n  [d] Skip (set manually)\n\n"
    printf "Choice [a/b/c/d]: "; read -r _llama_choice
    case "$_llama_choice" in
        a|A)
            command -v brew &>/dev/null || error "Homebrew not found. Install: https://brew.sh"
            info "Installing via Homebrew..."
            brew install llama.cpp
            LLAMA_BIN="$(command -v llama-server)"
            ;;
        b|B)
            info "Fetching latest release from ggerganov/llama.cpp..."
            LLAMA_BIN="$(_download_github_release)" \
                || error "GitHub download failed. Try option [c] to build from source."
            info "Downloaded: $LLAMA_BIN"
            ;;
        c|C) _build_from_source ;;
        d|D)
            warn "Skipping. Set LLAMA_SERVER_BIN in .env before running."
            LLAMA_BIN="llama-server"
            ;;
        *) error "Invalid choice." ;;
    esac
else
    info "Found: $LLAMA_BIN"
fi

# ── Model setup ───────────────────────────────────────────────────────────────
step "Model setup..."

HF_REPO_9B="sci4ai/Qwen3.5-9B-Abliterated-Q8_0-GGUF"
HF_REPO_27B="sci4ai/Qwen3.5-27B-Ablit-iQ4_XS.gguf"

_ram_gb() {
    "$PYTHON" -c "
import os
try:
    with open('/proc/meminfo') as f:
        for l in f:
            if l.startswith('MemTotal'):
                print(int(l.split()[1]) // 1048576); break
except Exception: print(0)
"
}
RAM_GB="$(_ram_gb)"
if [[ "$RAM_GB" -ge 16 ]]; then
    DEFAULT_HF_REPO="$HF_REPO_27B"
    info "RAM: ${RAM_GB}GB — defaulting to 27B model"
else
    DEFAULT_HF_REPO="$HF_REPO_9B"
    info "RAM: ${RAM_GB}GB — defaulting to 9B model"
fi

CHOSEN_MODEL=""

printf "Scan home directory for existing GGUF models? [y/N]: "; read -r _scan_ans
mapfile -t MODELS < <([[ "${_scan_ans,,}" =~ ^y ]] && scan_models || true)

_hf_download() {
    local _repo="$1"
    "$PYTHON" - "$_repo" <<'PYEOF'
import urllib.request, json, sys, os
from pathlib import Path

repo = sys.argv[1]
out_dir = Path.home() / "models" / repo.split("/")[-1]
out_dir.mkdir(parents=True, exist_ok=True)
hdrs = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=20) as r:
        return r.read()

try:
    meta = json.loads(fetch(f"https://huggingface.co/api/models/{repo}?expand[]=siblings"))
except Exception as e:
    print(f"ERROR fetching repo metadata: {e}", file=sys.stderr); sys.exit(1)

files = [s["rfilename"] for s in meta.get("siblings", []) if s["rfilename"].endswith(".gguf")]
if not files:
    print("ERROR: no .gguf files found in repo", file=sys.stderr); sys.exit(1)

if len(files) == 1:
    fname = files[0]
else:
    print(f"\nGGUF files in {repo}:", file=sys.stderr)
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f}", file=sys.stderr)
    raw = input("Select [1]: ").strip()
    idx = (int(raw) - 1) if raw.isdigit() else 0
    fname = files[max(0, min(idx, len(files) - 1))]

dest = out_dir / fname
if dest.exists():
    print(f"Already downloaded: {dest}", file=sys.stderr)
    print(str(dest)); sys.exit(0)

url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
print(f"Downloading {fname} → {dest}", file=sys.stderr)
try:
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req) as r:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk: break
                f.write(chunk); done += len(chunk)
                if total:
                    pct = min(100, done * 100 // total)
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    print(f"\r  [{bar}] {pct}%  ", end="", flush=True, file=sys.stderr)
    print(file=sys.stderr)
except Exception as e:
    dest.unlink(missing_ok=True)
    print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)

print(str(dest))
PYEOF
}

if [[ ${#MODELS[@]} -gt 0 ]]; then
    printf "\nFound local models:\n"
    for _i in "${!MODELS[@]}"; do
        printf "  [%d] %s\n" "$((_i + 1))" "${MODELS[$_i]}"
    done
    printf "  [D] Download from HuggingFace\n"
    printf "  [P] Enter local path\n\n"
    printf "Select [1-%d / D / P]: " "${#MODELS[@]}"; read -r _sel

    if [[ "${_sel,,}" == "p" ]]; then
        printf "Path: "; read -r CHOSEN_MODEL
    elif [[ "${_sel,,}" != "d" ]]; then
        if [[ "$_sel" =~ ^[0-9]+$ && "$_sel" -ge 1 && "$_sel" -le "${#MODELS[@]}" ]]; then
            CHOSEN_MODEL="${MODELS[$((_sel - 1))]}"
        else
            error "Invalid selection."
        fi
    fi
fi

if [[ -z "$CHOSEN_MODEL" ]]; then
    [[ ${#MODELS[@]} -eq 0 ]] && warn "No local .gguf models found."
    printf "\nEnter a HuggingFace repo ID or local path.\n"
    printf "  [1] %s (9B, ~9GB)\n" "$HF_REPO_9B"
    printf "  [2] %s (27B, ~14GB)\n" "$HF_REPO_27B"
    printf "  [Enter] = default for your RAM (%s)\n\n" "$DEFAULT_HF_REPO"
    printf "Repo/path/1/2: "; read -r _model_input
    case "$_model_input" in
        1) _model_input="$HF_REPO_9B" ;;
        2) _model_input="$HF_REPO_27B" ;;
        "") _model_input="$DEFAULT_HF_REPO" ;;
    esac

    if [[ -f "$_model_input" || "$_model_input" == /* || "$_model_input" == ~* ]]; then
        CHOSEN_MODEL="${_model_input/#\~/$HOME}"
        [[ -f "$CHOSEN_MODEL" ]] || warn "File not found — update MODEL in .env after install."
    else
        info "Downloading from HuggingFace: $_model_input"
        CHOSEN_MODEL="$(_hf_download "$_model_input")" \
            || error "Download failed. Check network or set MODEL in .env manually."
    fi
fi

[[ -n "$CHOSEN_MODEL" ]] || error "No model selected."
info "Model: $CHOSEN_MODEL"
MODEL_ALIAS="$(basename "${CHOSEN_MODEL%.gguf}")"

# ── GPU layers ────────────────────────────────────────────────────────────────
GPU_BACKEND="${GPU_BACKEND:-$(detect_gpu)}"
[[ "$GPU_BACKEND" == "cpu" ]] && NGL_DEFAULT=0 || NGL_DEFAULT=99
printf "GPU layers to offload (0=CPU-only, 99=fully GPU) [%d]: " "$NGL_DEFAULT"
read -r _ngl; NGL_LAYERS="${_ngl:-$NGL_DEFAULT}"

# ── Conversation storage ──────────────────────────────────────────────────────
step "Conversation storage..."
printf "  [1] SQLite   — full search, tasks, folders (recommended)\n"
printf "  [2] JSONL    — flat files per conversation, easy to back up\n"
printf "  [3] None     — no history stored\n\n"
while true; do
    printf "Storage [1/2/3]: "; read -r _sc
    case "$_sc" in
        1) CONV_STORAGE="sqlite"; break ;;
        2) CONV_STORAGE="jsonl";  break ;;
        3) CONV_STORAGE="none";
           warn "Conversations will not be saved across sessions."; break ;;
        *) printf "Enter 1, 2, or 3.\n" ;;
    esac
done

# ── Port scan ─────────────────────────────────────────────────────────────────
step "Finding available ports..."
LLAMA_PORT="$(find_free_port 8080 8180)"
TOOLS_PORT="$(find_free_port 5100 5200)"
BACKEND_PORT="$(find_free_port 5000 5099)"
FRONTEND_PORT="$(find_free_port 3000 3100)"
info "llama-server=$LLAMA_PORT  tools=$TOOLS_PORT  backend=$BACKEND_PORT  frontend=$FRONTEND_PORT"

# ── Python deps ───────────────────────────────────────────────────────────────
step "Installing Python dependencies..."
if command -v uv &>/dev/null; then
    uv sync
    RUNPY="uv run python"
    info "Installed via uv"
else
    warn "uv not found — falling back to pip + requirements.txt"
    "$PYTHON" -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
    RUNPY=".venv/bin/python"
    info "Installed via pip"
fi

# ── Frontend deps ─────────────────────────────────────────────────────────────
step "Installing frontend dependencies..."
if command -v npm &>/dev/null; then
    npm install --prefix frontend --silent
    info "Frontend deps installed."
else
    warn "npm not found — skipping frontend deps."
    warn "Install Node.js then run: npm install --prefix frontend"
fi

# ── Data directory ────────────────────────────────────────────────────────────
DATA_DIR="${HOME}/.atomic_chat"
mkdir -p "$DATA_DIR"
SQLITE_URL="sqlite:///${DATA_DIR}/atomic_chat.db"
JSONL_DIR="${DATA_DIR}/conversations"

# ── Secret key ────────────────────────────────────────────────────────────────
SECRET_KEY="$("$PYTHON" -c "import secrets; print(secrets.token_hex(32))")"

# ── Write .env ────────────────────────────────────────────────────────────────
step "Writing .env..."
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/.env" "$SCRIPT_DIR/.env.bak"
    warn "Backed up existing .env → .env.bak"
fi

cat > "$SCRIPT_DIR/.env" <<ENVEOF
# ── Flask ──────────────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
BACKEND_PORT=${BACKEND_PORT}

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL=${SQLITE_URL}
CONVERSATION_STORAGE=${CONV_STORAGE}
JSONL_PATH=${JSONL_DIR}

# ── llama-server ───────────────────────────────────────────────────────────────
LLAMA_HOST=127.0.0.1
LLAMA_PORT=${LLAMA_PORT}
LLAMA_SERVER_URL=http://127.0.0.1:${LLAMA_PORT}
LLAMA_ARG_CTX_SIZE=32000

# ── Model ──────────────────────────────────────────────────────────────────────
MODEL=${CHOSEN_MODEL}
MODEL_ALIAS=${MODEL_ALIAS}
DEFAULT_MODEL=${MODEL_ALIAS}
MODEL_NGL=${NGL_LAYERS}
MODEL_CTX=32000

# ── Service ports ──────────────────────────────────────────────────────────────
TOOLS_PORT=${TOOLS_PORT}
FRONTEND_PORT=${FRONTEND_PORT}

# ── Workspace ──────────────────────────────────────────────────────────────────
DEFAULT_WORKSPACE=${DATA_DIR}/workspace/
ENVEOF
chmod 600 "$SCRIPT_DIR/.env"
info "Written: .env"

# ── DB init ───────────────────────────────────────────────────────────────────
if [[ "$CONV_STORAGE" == "sqlite" ]]; then
    step "Initialising database..."
    DATABASE_URL="$SQLITE_URL" $RUNPY -c "from auth.db import init_db; init_db()"
    info "Database ready: $SQLITE_URL"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
printf "\n${GREEN}${BOLD}══════════════════════════════════${RESET}\n"
printf "${GREEN}${BOLD}  Installation complete!${RESET}\n"
printf "${GREEN}${BOLD}══════════════════════════════════${RESET}\n\n"
info "Start everything:  ./start.sh"
printf "\n"
info "Or launch llama-server manually:"
printf "  %s \\\\\n    --model \"%s\" \\\\\n    --port %s \\\\\n    -ngl %s\n\n" \
    "$LLAMA_BIN" "$CHOSEN_MODEL" "$LLAMA_PORT" "$NGL_LAYERS"
info "UI: http://localhost:${FRONTEND_PORT}"
printf "\n"

fi  # end PATH 1

# ══════════════════════════════════════════════════════════════════════════════
# PATH 2 — CLOUD CLIENT ONLY
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$INSTALL_PATH" == "cloud" ]]; then

# ── Client venv ───────────────────────────────────────────────────────────────
step "Setting up client environment..."
VENV_DIR="$SCRIPT_DIR/.client-venv"
VENV_PY="$VENV_DIR/bin/python"

if [[ -d "$VENV_DIR" ]]; then
    warn "Reusing existing .client-venv"
else
    "$PYTHON" -m venv "$VENV_DIR"
fi
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet websockets rich requests python-dotenv cryptography
info "Client dependencies installed."

# ── Port ──────────────────────────────────────────────────────────────────────
step "Finding free port for agent bridge..."
AGENT_PORT="$(find_free_port 5100 5200)"
info "Agent bridge port: $AGENT_PORT"

# ── API key ───────────────────────────────────────────────────────────────────
printf "\nYou'll need an API key to connect (or press Enter to configure later).\n"
printf "API key: "; read -r _api_key

# ── Write .env.client ─────────────────────────────────────────────────────────
cat > "$SCRIPT_DIR/.env.client" <<ENVEOF
INSTALL_MODE=cloud
AGENT_API_KEY=${_api_key:-YOUR_KEY_HERE}
ATOMIC_HOST=https://agent.eric-merritt.com
AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws
CLIENT_AGENT_PORT=${AGENT_PORT}
ALLOWED_PATHS=${HOME}
ENVEOF
chmod 600 "$SCRIPT_DIR/.env.client"
info "Written: .env.client"

[[ -z "${_api_key:-}" ]] && warn "Set AGENT_API_KEY in .env.client before running."

# ── ./agent wrapper ───────────────────────────────────────────────────────────
cat > "$SCRIPT_DIR/agent" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$DIR/.env.client" ]] && { set -a; source "$DIR/.env.client"; set +a; }
exec "$DIR/.client-venv/bin/python" "$DIR/atomic_client/agent.py" "$@"
WRAPPER
chmod +x "$SCRIPT_DIR/agent"
info "Created: ./agent"

# ── .gitignore ────────────────────────────────────────────────────────────────
for _pat in ".client-venv" ".env.client"; do
    grep -qxF "$_pat" "$SCRIPT_DIR/.gitignore" 2>/dev/null || echo "$_pat" >> "$SCRIPT_DIR/.gitignore"
done

# ── Done ─────────────────────────────────────────────────────────────────────
printf "\n${GREEN}${BOLD}══════════════════════════════════${RESET}\n"
printf "${GREEN}${BOLD}  Installation complete!${RESET}\n"
printf "${GREEN}${BOLD}══════════════════════════════════${RESET}\n\n"
info "Start the agent bridge:  ./agent"
printf "\nYour browser will open for login on first run.\n\n"

fi  # end PATH 2
