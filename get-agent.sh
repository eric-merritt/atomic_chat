#!/usr/bin/env bash
# get-agent.sh — Download and install the Atomic Chat client agent
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main/get-agent.sh | bash
#
# Or with a custom directory:
#   curl -fsSL https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main/get-agent.sh | bash -s -- ~/my-agent

set -euo pipefail

BASE_URL="https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main"
FILES=(client_agent.py install_client.sh)

INSTALL_DIR="${1:-./agent-client}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { echo -e "${GREEN}[+]${RESET} $*"; }
error() { echo -e "${RED}[x]${RESET} $*"; exit 1; }

# Check for curl or wget
if command -v curl &>/dev/null; then
    fetch() { curl -fsSL "$1"; }
elif command -v wget &>/dev/null; then
    fetch() { wget -qO- "$1"; }
else
    error "curl or wget is required"
fi

echo -e "${BOLD}Atomic Chat — Client Agent Installer${RESET}"
echo "======================================"
echo

mkdir -p "$INSTALL_DIR"

for file in "${FILES[@]}"; do
    info "Downloading $file..."
    fetch "$BASE_URL/$file" > "$INSTALL_DIR/$file"
done

chmod +x "$INSTALL_DIR/install_client.sh"

info "Running installer..."
echo
cd "$INSTALL_DIR" && bash ./install_client.sh
