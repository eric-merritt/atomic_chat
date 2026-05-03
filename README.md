# Atomic Chat

Agentic chat platform pairing llama.cpp with 90+ tools. Run fully local with your own LLM, or connect to the hosted service at [agent.eric-merritt.com](https://agent.eric-merritt.com).

---

## Two paths

### Path 1 — Full Local Stack

Run everything on your own machine: llama-server, Flask backend, React frontend. No external services required.

**What you get:** A full web UI at `localhost`, your own model, complete data privacy.

**Requirements:** Python 3.12+, Node.js, and enough RAM/VRAM for your chosen model.

---

#### Linux / macOS

```bash
bash install_client.sh
# Choose option [1] at the prompt
```

The script will:
1. Locate or install `llama-server` — Homebrew on Mac, download the matching pre-built release from [ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp) (CUDA for NVIDIA, Vulkan for Intel Arc / AMD, AVX2 for CPU), or build from source
2. Let you scan for existing `.gguf` models, download one from HuggingFace, or enter a path manually — defaults to `sci4ai/Qwen3.5-27B-Ablit-iQ4_XS.gguf` on 16GB+ RAM, `sci4ai/Qwen3.5-9B-Abliterated-Q8_0-GGUF` on less
3. Auto-detect GPU and prompt for offload layers
4. Install Python dependencies via `uv` (or pip fallback)
5. Install frontend dependencies via `npm`
6. Pick free ports and generate a secret key
7. Write `.env` and initialise the database

**Start:**
```bash
./start.sh
# UI opens at http://localhost:<frontend-port>
```

---

#### Windows

```powershell
.\install_client.ps1
# Choose option [1] at the prompt
```

The script will:
1. Check for Python 3.12+ (offers to install if missing)
2. Locate or download `llama-server.exe` (winget, GitHub release, or skip)
3. Let you scan for existing `.gguf` models, download from HuggingFace, or enter a path
4. Auto-detect NVIDIA/AMD/Intel GPU and prompt for offload layers
5. Install `uv` if missing, run `uv sync`
6. Run `npm install` for the frontend
7. Pick free ports, generate a secret key, write `.env`, initialise the database

**Start:**
```
start_local.bat
```

---

### Path 2 — Cloud Client Only

Install a lightweight agent that bridges your local filesystem to the hosted service. No local model or backend required.

**What you get:** Access to all tools (filesystem, bash, web) from the [agent.eric-merritt.com](https://agent.eric-merritt.com) interface, with files served from your machine.

**Requirements:** Python 3.12+ (Linux/macOS/Windows) — or just the MSI on Windows.

---

#### Linux / macOS

```bash
bash install_client.sh
# Choose option [2] at the prompt
```

The script will:
1. Create a Python virtualenv and install the agent dependencies
2. Write `.env.client` with the server URL and `ALLOWED_PATHS=$HOME`
3. Create an `./agent` launcher script

**Start:**
```bash
./agent
# Opens your browser for one-time authentication, then stays connected
```

---

#### Windows — MSI (recommended for non-technical users)

Download `atomic-chat-setup.msi` from the [latest release](../../releases/latest) and double-click it. The agent installs to `%LOCALAPPDATA%\AtomicChat\` with a Start Menu shortcut.

**Start:** Launch **Atomic Chat Agent** from the Start Menu. Your browser will open for one-time authentication.

---

#### Windows — PowerShell script

```powershell
.\install_client.ps1
# Choose option [2] at the prompt
```

**Start:**
```
agent.bat
```

---

## Configuration

Both paths write a config file on first install:

| Path | Config file | Key settings |
|------|-------------|--------------|
| Full local | `.env` | `MODEL`, `LLAMA_PORT`, `BACKEND_PORT`, `FRONTEND_PORT` |
| Cloud client | `.env.client` | `AGENT_SERVER`, `ALLOWED_PATHS` |

**`ALLOWED_PATHS`** controls which directories the agent can read and write. It defaults to your home directory. Add more paths as a comma-separated list:

```
ALLOWED_PATHS=/home/you,/mnt/data
```

On Windows:
```
ALLOWED_PATHS=C:\Users\you,D:\projects
```

---

## Development

```bash
# Backend
uv run python main.py

# Frontend
cd frontend && npm run dev

# Tests
pytest
npx vitest run
```
