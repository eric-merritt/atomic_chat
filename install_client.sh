#!/usr/bin/env bash
# install_client.sh — Set up the client agent for agent.eric-merritt.com
#
# Usage:
#   git clone <repo-url> && cd <repo>
#   ./install_client.sh
#
# What it does:
#   1. Checks Python >= 3.12
#   2. Creates a venv and installs the one dependency (websockets)
#   3. Prompts for your API key and saves it to .env
#   4. Creates a convenience wrapper: ./agent
#
# After install, run:
#   ./agent                              # interactive chat
#   ./agent -m "list files in ~/code"    # one-shot
#   ./agent --allow-writes -m "fix it"   # enable write tools

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[+]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[!]${RESET} $*"; }
error() { echo -e "${RED}[x]${RESET} $*"; exit 1; }

# ── Locate project root (directory containing this script) ───────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}Agent Client Installer${RESET}"
echo "======================================"
echo

# ── 1. Check Python ─────────────────────────────────────────────────────────
info "Checking Python..."

PYTHON=""
for cmd in python3.12 python3.13 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major="${ver%%.*}"
        minor="${ver##*.}"
        if [[ "$major" -ge 3 && "$minor" -ge 12 ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    warn "Python >= 3.12 not found."
    read -rp "Do you want to install Python 3.12? (Y/N): " answer
    if [[ "$answer" =~ ^[Yy] ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            if command -v brew &>/dev/null; then
                info "Installing Python 3.12 via Homebrew..."
                brew install python@3.12
                PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
            else
                error "Homebrew not found. Install it first: https://brew.sh\n  Then re-run this script."
            fi
        elif command -v apt-get &>/dev/null; then
            info "Installing Python 3.12 via apt..."
            sudo apt-get update -qq && sudo apt-get install -y python3.12 python3.12-venv
            PYTHON="python3.12"
        elif command -v dnf &>/dev/null; then
            info "Installing Python 3.12 via dnf..."
            sudo dnf install -y python3.12
            PYTHON="python3.12"
        elif command -v pacman &>/dev/null; then
            info "Installing Python 3.12 via pacman..."
            sudo pacman -S --noconfirm python
            PYTHON="python3"
        else
            error "Could not detect package manager. Install Python 3.12 manually:\n  https://www.python.org/downloads/"
        fi

        # Verify it worked
        if ! command -v "$PYTHON" &>/dev/null; then
            error "Python installation failed. Install manually from https://www.python.org/downloads/"
        fi
        info "Python installed successfully!"
    else
        error "Python >= 3.12 is required. Install it first:\n  Ubuntu/Debian: sudo apt install python3.12\n  macOS: brew install python@3.12\n  Other: https://www.python.org/downloads/"
    fi
fi

info "Using $PYTHON ($("$PYTHON" --version 2>&1))"

# ── 2. Create venv ──────────────────────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.client-venv"

if [[ -d "$VENV_DIR" ]]; then
    warn "Virtual environment already exists at .client-venv"
else
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

info "Installing dependencies..."
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet websockets

# ── 3. API key ──────────────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env.client"

if [[ -f "$ENV_FILE" ]]; then
    warn "Config file .env.client already exists — skipping key setup"
    warn "Edit .env.client to change your key"
else
    echo
    echo -e "${BOLD}API Key Setup${RESET}"
    echo "You need an external API key for agent.eric-merritt.com."
    echo "Contact the server admin to get one."
    echo
    read -rp "Paste your API key (or press Enter to skip for now): " api_key

    if [[ -n "$api_key" ]]; then
        cat > "$ENV_FILE" <<EOF
AGENT_API_KEY=$api_key
AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws
EOF
        chmod 600 "$ENV_FILE"
        info "Saved to .env.client (mode 600)"
    else
        cat > "$ENV_FILE" <<EOF
AGENT_API_KEY=YOUR_KEY_HERE
AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws
EOF
        chmod 600 "$ENV_FILE"
        warn "Placeholder saved to .env.client — edit it before running"
    fi
fi

# ── 4. Create wrapper script ────────────────────────────────────────────────
WRAPPER="$SCRIPT_DIR/agent"

cat > "$WRAPPER" <<'WRAPPER_EOF'
#!/usr/bin/env bash
# Convenience wrapper for client_agent.py
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load config
if [[ -f "$SCRIPT_DIR/.env.client" ]]; then
    set -a
    source "$SCRIPT_DIR/.env.client"
    set +a
fi

exec "$SCRIPT_DIR/.client-venv/bin/python" "$SCRIPT_DIR/client_agent.py" "$@"
WRAPPER_EOF

chmod +x "$WRAPPER"

# ── 5. Add to .gitignore ───────────────────────────────────────────────────
GITIGNORE="$SCRIPT_DIR/.gitignore"
for pattern in ".client-venv" ".env.client"; do
    if ! grep -qxF "$pattern" "$GITIGNORE" 2>/dev/null; then
        echo "$pattern" >> "$GITIGNORE"
    fi
done

# ── Done ────────────────────────────────────────────────────────────────────
echo
echo -e "${GREEN}=====================================${RESET}"
echo -e "${GREEN}  Installation complete!${RESET}"
echo -e "${GREEN}=====================================${RESET}"
echo
echo "Quick start:"
echo "  ./agent                                  # interactive chat"
echo "  ./agent -m 'list files in ~/projects'    # one-shot"
echo "  ./agent --allow-writes -m 'fix main.py'  # enable writes"
echo
echo "Configuration:  .env.client"
echo "  AGENT_API_KEY  — your API key"
echo "  AGENT_SERVER   — server URL (default: wss://agent.eric-merritt.com/api/chat/ws)"
echo
if grep -q "YOUR_KEY_HERE" "$ENV_FILE" 2>/dev/null; then
    warn "Don't forget to set your API key in .env.client!"
fi
