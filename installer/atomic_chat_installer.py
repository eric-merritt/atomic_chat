"""
Atomic Chat — Windows Setup
Handles both Path 1 (Full Local Stack) and Path 2 (Cloud Client Only).
Compiled to atomic-chat-setup.exe via PyInstaller.
"""

import ctypes
import json
import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ── ANSI colours (Windows 10+ supports VT100 via ENABLE_VIRTUAL_TERMINAL_PROCESSING) ──
def _enable_ansi():
    if platform.system() == "Windows":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

_enable_ansi()

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def info(msg):  print(f"{GREEN}[+]{RESET} {msg}")
def warn(msg):  print(f"{YELLOW}[!]{RESET} {msg}")
def step(msg):  print(f"\n{CYAN}{BOLD}▶ {msg}{RESET}")
def fail(msg):  print(f"\033[91m[x]{RESET} {msg}"); sys.exit(1)

INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AtomicChat"
GITHUB_REPO = "eric-merritt/atomic_chat"
LLAMA_REPO  = "ggerganov/llama.cpp"

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "atomic-chat-installer",
        "Accept": "application/json",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def download(url, dest: Path, label=""):
    req = urllib.request.Request(url, headers={"User-Agent": "atomic-chat-installer"})
    with urllib.request.urlopen(req, timeout=600) as r:
        total = int(r.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = min(100, done * 100 // total)
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    print(f"\r  [{bar}] {pct}%  ", end="", flush=True)
    if total:
        print()

def find_free_port(start, end):
    for p in range(start, end + 1):
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", p))
                return p
            except OSError:
                pass
    fail(f"No free port in {start}-{end}")

def run(*args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        fail(f"Command failed: {' '.join(str(a) for a in args)}")
    return result

def find_python():
    for cmd in ("python", "python3", "py"):
        try:
            r = subprocess.run([cmd, "-c",
                "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                major, minor = map(int, r.stdout.strip().split("."))
                if major >= 3 and minor >= 12:
                    return cmd
        except Exception:
            pass
    return None

def find_node():
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def ram_gb():
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys // (1024 ** 3)
    except Exception:
        return 0

def detect_gpu():
    try:
        import subprocess
        gpus = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "Name"],
            capture_output=True, text=True, timeout=10).stdout.lower()
        if "nvidia" in gpus:
            cuda = Path("C:/Windows/System32/nvcuda.dll")
            return "cuda" if cuda.exists() else "vulkan"
        if "amd" in gpus or "radeon" in gpus or "intel arc" in gpus or "intel xe" in gpus:
            return "vulkan"
    except Exception:
        pass
    return "cpu"

def scan_models():
    dirs = [
        Path.home() / "models",
        Path.home() / ".cache" / "llama.cpp",
        Path.home() / ".cache" / "huggingface" / "hub",
        Path(os.environ.get("LOCALAPPDATA", "")) / "lm-studio" / "models",
        Path("C:/models"),
    ]
    found = []
    for d in dirs:
        if d.exists():
            found.extend(sorted(d.rglob("*.gguf")))
    return found

# ── llama-server download ──────────────────────────────────────────────────────

def download_llama_server(gpu: str, dest_dir: Path) -> Path:
    info("Fetching latest llama.cpp release...")
    release = fetch_json(f"https://api.github.com/repos/{LLAMA_REPO}/releases/latest")
    assets  = release.get("assets", [])

    # cuda/rocm/vulkan/cpu → asset name patterns (priority order)
    patterns = {
        "cuda":   ["win-cuda-cu", "win-cuda"],
        "vulkan": ["win-vulkan-x64"],
        "rocm":   ["win-vulkan-x64"],
        "cpu":    ["win-avx2-x64", "win-x64"],
    }
    fallback = ["win-avx2-x64", "win-x64"]

    asset = None
    for pat in patterns.get(gpu, []) + fallback:
        for a in assets:
            if pat.lower() in a["name"].lower() and a["name"].endswith(".zip"):
                asset = a
                break
        if asset:
            break

    if not asset:
        fail("No matching Windows llama.cpp release found. "
             "Download manually from https://github.com/ggerganov/llama.cpp/releases")

    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / asset["name"]
    info(f"Downloading {asset['name']} ({asset['size'] >> 20} MB)...")
    download(asset["browser_download_url"], zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink()

    matches = sorted(dest_dir.rglob("llama-server.exe"))
    if not matches:
        fail("llama-server.exe not found in downloaded archive.")
    return matches[0]

# ── HuggingFace model download ─────────────────────────────────────────────────

HF_REPO_9B  = "sci4ai/Qwen3.5-9B-Abliterated-Q8_0-GGUF"
HF_REPO_27B = "sci4ai/Qwen3.5-27B-Ablit-iQ4_XS.gguf"

def hf_download(repo: str, out_dir: Path) -> Path:
    hf_token = os.environ.get("HF_TOKEN", "")
    hdrs = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}

    info(f"Fetching file list: {repo}")
    meta  = fetch_json(f"https://huggingface.co/api/models/{repo}?expand[]=siblings", hdrs)
    files = [s["rfilename"] for s in meta.get("siblings", []) if s["rfilename"].endswith(".gguf")]

    if not files:
        fail(f"No .gguf files found in {repo}")

    if len(files) == 1:
        fname = files[0]
    else:
        print("\nAvailable GGUF files:")
        for i, f in enumerate(files, 1):
            print(f"  [{i}] {f}")
        raw = input(f"Select [1-{len(files)}]: ").strip()
        idx = (int(raw) - 1) if raw.isdigit() else 0
        fname = files[max(0, min(idx, len(files) - 1))]

    dest = out_dir / repo.split("/")[-1] / fname
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        info(f"Already downloaded: {dest}")
        return dest

    url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
    info(f"Downloading {fname}...")
    req = urllib.request.Request(url, headers={"User-Agent": "atomic-chat-installer", **hdrs})
    with urllib.request.urlopen(req, timeout=600) as r:
        total = int(r.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = min(100, done * 100 // total)
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    print(f"\r  [{bar}] {pct}%  ", end="", flush=True)
    print()
    return dest

# ── App source download ────────────────────────────────────────────────────────

def ensure_app_source(app_dir: Path):
    if (app_dir / "main.py").exists():
        info(f"App source already present: {app_dir}")
        return

    info("Downloading Atomic Chat source...")
    release = fetch_json(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")
    zip_url = release.get("zipball_url")
    if not zip_url:
        # Fall back to main branch zip
        zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"

    zip_path = app_dir.parent / "atomic_chat_src.zip"
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    download(zip_url, zip_path, "source")

    with zipfile.ZipFile(zip_path) as zf:
        top = zf.namelist()[0].rstrip("/")
        zf.extractall(app_dir.parent)
    zip_path.unlink()

    extracted = app_dir.parent / top
    if extracted != app_dir:
        if app_dir.exists():
            shutil.rmtree(app_dir)
        extracted.rename(app_dir)

    info(f"Source installed to {app_dir}")

# ── DB init ────────────────────────────────────────────────────────────────────

def init_db(app_dir: Path, python_cmd: str, db_url: str):
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [python_cmd, "-c", "from auth.db import init_db; init_db()"],
        cwd=app_dir, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        warn(f"DB init failed: {result.stderr.strip()}")
        warn("Run 'alembic upgrade head' manually after install.")
    else:
        info("Database ready.")

# ══════════════════════════════════════════════════════════════════════════════
# PATH 1 — FULL LOCAL STACK
# ══════════════════════════════════════════════════════════════════════════════

def install_local():
    app_dir   = INSTALL_DIR / "app"
    llama_dir = INSTALL_DIR / "llama-cpp"
    models_dir = Path.home() / "models"

    # ── Python ────────────────────────────────────────────────────────────────
    step("Checking Python...")
    python = find_python()
    if not python:
        warn("Python >= 3.12 not found.")
        ans = input("Download and install Python 3.12? [Y/N]: ").strip().lower()
        if ans == "y":
            py_url  = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
            py_tmp  = Path(os.environ["TEMP"]) / "python-3.12-installer.exe"
            info("Downloading Python 3.12...")
            download(py_url, py_tmp)
            subprocess.run([str(py_tmp), "/passive", "InstallAllUsers=0",
                            "PrependPath=1", "Include_launcher=1"], check=True)
            py_tmp.unlink(missing_ok=True)
            python = find_python()
            if not python:
                fail("Python not found after install. Re-open this installer.")
        else:
            fail("Python >= 3.12 required.")
    info(f"Python: {python}")

    # ── Node.js ───────────────────────────────────────────────────────────────
    step("Checking Node.js...")
    if not find_node():
        warn("Node.js not found.")
        ans = input("Install via winget? [Y/N]: ").strip().lower()
        if ans == "y":
            subprocess.run(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS",
                            "--accept-package-agreements", "--accept-source-agreements"])
        else:
            warn("Skipping. Run 'npm install --prefix app\\frontend' manually after install.")
    else:
        info("Node.js found.")

    # ── App source ────────────────────────────────────────────────────────────
    step("Setting up app source...")
    ensure_app_source(app_dir)

    # ── llama-server ──────────────────────────────────────────────────────────
    step("Setting up llama-server...")
    llama_bin = None
    for cand in ["llama-server",
                 str(llama_dir / "llama-server.exe"),
                 str(INSTALL_DIR / "llama-cpp" / "llama-server.exe")]:
        try:
            r = subprocess.run([cand, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                llama_bin = cand
                break
        except Exception:
            pass
        if cand != "llama-server" and Path(cand).exists():
            llama_bin = cand
            break

    if not llama_bin:
        warn("llama-server not found.")
        print("\n  [a] Download pre-built release from GitHub (recommended)")
        print("  [b] winget (Windows Package Manager)")
        print("  [c] Skip — set LLAMA_SERVER_BIN in .env manually\n")
        choice = input("Choice [a/b/c]: ").strip().lower()
        if choice == "a":
            gpu = detect_gpu()
            info(f"Detected GPU: {gpu}")
            llama_bin = str(download_llama_server(gpu, llama_dir))
            info(f"Downloaded: {llama_bin}")
        elif choice == "b":
            try:
                subprocess.run(["winget", "install", "-e", "--id", "ggerganov.llama.cpp",
                                "--accept-package-agreements", "--accept-source-agreements"],
                               check=True)
                r = subprocess.run(["where", "llama-server"], capture_output=True, text=True)
                llama_bin = r.stdout.strip().splitlines()[0] if r.returncode == 0 else "llama-server"
            except Exception:
                warn("winget failed — set LLAMA_SERVER_BIN in .env manually.")
                llama_bin = "llama-server"
        else:
            warn("Skipping. Set LLAMA_SERVER_BIN in .env before running.")
            llama_bin = "llama-server"
    else:
        info(f"Found: {llama_bin}")

    # ── Model ─────────────────────────────────────────────────────────────────
    step("Model setup...")
    gb = ram_gb()
    default_repo = HF_REPO_27B if gb >= 16 else HF_REPO_9B
    info(f"RAM: {gb}GB — default model: {default_repo}")

    model_path = ""
    models = scan_models()
    if models:
        print("\nFound local models:")
        for i, m in enumerate(models, 1):
            print(f"  [{i}] {m}")
        print("  [0] Download from HuggingFace")
        print("  [m] Enter path manually\n")
        sel = input(f"Select [0-{len(models)}/m]: ").strip().lower()
        if sel == "m":
            model_path = input("Path: ").strip()
        elif sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(models):
                model_path = str(models[idx - 1])

    if not model_path:
        print(f"\n  [1] {HF_REPO_9B} (9B, ~9GB)")
        print(f"  [2] {HF_REPO_27B} (27B, ~14GB)")
        print(f"  [Enter] default for your RAM ({default_repo})\n")
        sel = input("Repo/path/1/2: ").strip()
        repo = {
            "1": HF_REPO_9B,
            "2": HF_REPO_27B,
            "":  default_repo,
        }.get(sel, sel)

        if Path(repo).exists():
            model_path = repo
        elif "/" in repo:
            model_path = str(hf_download(repo, models_dir))
        else:
            fail(f"Cannot interpret '{repo}' as a path or HuggingFace repo.")

    if not model_path:
        fail("No model selected.")
    info(f"Model: {model_path}")
    model_alias = Path(model_path).stem.replace(" ", "-")

    # ── GPU layers ────────────────────────────────────────────────────────────
    step("GPU offload layers...")
    gpu = detect_gpu()
    default_ngl = "0" if gpu == "cpu" else "99"
    info(f"Detected GPU: {gpu}")
    ngl = input(f"GPU layers (0=CPU only, 99=all) [{default_ngl}]: ").strip() or default_ngl

    # ── Conversation storage ──────────────────────────────────────────────────
    step("Conversation storage...")
    print("  [1] SQLite   — full search, tasks, folders (recommended)")
    print("  [2] JSONL    — flat files per conversation")
    print("  [3] None     — no history stored\n")
    conv_storage = None
    while not conv_storage:
        sel = input("Storage [1/2/3]: ").strip()
        conv_storage = {"1": "sqlite", "2": "jsonl", "3": "none"}.get(sel)
        if not conv_storage:
            print("Enter 1, 2, or 3.")

    # ── uv / pip ──────────────────────────────────────────────────────────────
    step("Installing Python dependencies...")
    uv = shutil.which("uv")
    if not uv:
        info("Installing uv...")
        subprocess.run([python, "-m", "pip", "install", "--quiet", "uv"], check=True)
        uv = shutil.which("uv")

    if uv:
        run(uv, "sync", cwd=app_dir)
        run_py = f'"{uv}" run python'
        python_cmd = uv
        use_uv = True
    else:
        warn("uv unavailable — falling back to pip")
        venv = app_dir / ".venv"
        run(python, "-m", "venv", str(venv))
        pip = str(venv / "Scripts" / "pip.exe")
        run(pip, "install", "--quiet", "-r", str(app_dir / "requirements.txt"))
        python_cmd = str(venv / "Scripts" / "python.exe")
        use_uv = False

    # ── npm ───────────────────────────────────────────────────────────────────
    step("Installing frontend dependencies...")
    if find_node():
        run("npm", "--prefix", str(app_dir / "frontend"), "install", cwd=app_dir)
        info("Frontend deps installed.")
    else:
        warn("npm not found — skipping frontend install.")

    # ── Ports ─────────────────────────────────────────────────────────────────
    step("Finding available ports...")
    llama_port   = find_free_port(8080, 8180)
    tools_port   = find_free_port(5100, 5200)
    backend_port = find_free_port(5000, 5099)
    frontend_port = find_free_port(5173, 5273)
    info(f"llama: {llama_port}  tools: {tools_port}  backend: {backend_port}  frontend: {frontend_port}")

    # ── Data dir + secret key ─────────────────────────────────────────────────
    import secrets
    data_dir  = INSTALL_DIR / "data"
    jsonl_dir = data_dir / "conversations"
    db_path   = data_dir / "atomic_chat.db"
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "logs").mkdir(exist_ok=True)
    secret_key = secrets.token_hex(32)
    db_url = f"sqlite:///{db_path}".replace("\\", "/")

    # ── .env ──────────────────────────────────────────────────────────────────
    step("Writing .env...")
    env_path = app_dir / ".env"
    env_path.write_text(f"""\
MODEL={model_path}
MODEL_ALIAS={model_alias}
MODEL_NGL={ngl}
MODEL_CTX=32000
LLAMA_SERVER_BIN={llama_bin}
LLAMA_PORT={llama_port}
LLAMA_HOST=127.0.0.1
LLAMA_SERVER_URL=http://127.0.0.1:{llama_port}
LLAMA_ARG_CTX_SIZE=32000
TOOLS_PORT={tools_port}
BACKEND_PORT={backend_port}
FRONTEND_PORT={frontend_port}
SECRET_KEY={secret_key}
DATABASE_URL={db_url}
CONVERSATION_STORAGE={conv_storage}
JSONL_PATH={jsonl_dir}
DEFAULT_WORKSPACE={data_dir / 'workspace'}
""", encoding="utf-8")
    env_path.chmod(env_path.stat().st_mode & ~(stat.S_IRGRP | stat.S_IROTH))
    info(f"Written: {env_path}")

    # ── DB init ───────────────────────────────────────────────────────────────
    if conv_storage == "sqlite":
        step("Initialising database...")
        if use_uv:
            env = {**os.environ, "DATABASE_URL": db_url}
            subprocess.run([uv, "run", "alembic", "upgrade", "head"],
                           cwd=app_dir, env=env)
        else:
            init_db(app_dir, python_cmd, db_url)

    # ── start_local.bat ───────────────────────────────────────────────────────
    step("Creating start_local.bat...")
    start_bat = INSTALL_DIR / "start_local.bat"
    uv_cmd = f'"{uv}"' if uv else "python"
    start_bat.write_text(f"""\
@echo off
setlocal enabledelayedexpansion
set "APP={app_dir}"
cd /d "%APP%"

for /f "usebackq tokens=1,* delims==" %%A in ("%APP%\\.env") do (
    set "_k=%%A"
    if not "!_k!"=="" if not "!_k:~0,1!"=="#" set "%%A=%%B"
)

echo Starting Atomic Chat (local mode)...

start "llama-server" /MIN cmd /k "%LLAMA_SERVER_BIN%" --model "%MODEL%" --host 0.0.0.0 --port %LLAMA_PORT% -ngl %MODEL_NGL% --alias "%MODEL_ALIAS%"
timeout /t 3 /nobreak > nul

start "tools-server" /MIN cmd /k {uv_cmd} run python "%APP%\\tools_server.py"
start "backend"      /MIN cmd /k {uv_cmd} run python "%APP%\\main.py" --serve
start "frontend"     /MIN cmd /k npm --prefix "%APP%\\frontend" run dev

echo.
echo Services started. Open: http://localhost:{frontend_port}
""", encoding="utf-8")

    # ── Desktop shortcut ──────────────────────────────────────────────────────
    _create_shortcut(
        name="Atomic Chat (Local)",
        target=str(start_bat),
        icon=str(app_dir / "frontend" / "public" / "favicon.ico"),
        description="Start Atomic Chat local stack",
    )

    print(f"\n{GREEN}{BOLD}══════════════════════════════════{RESET}")
    print(f"{GREEN}{BOLD}  Installation complete!{RESET}")
    print(f"{GREEN}{BOLD}══════════════════════════════════{RESET}\n")
    info(f"Start: double-click 'Atomic Chat (Local)' on your Desktop, or run:")
    print(f"  {start_bat}")
    print(f"\nUI will open at: http://localhost:{frontend_port}\n")

# ══════════════════════════════════════════════════════════════════════════════
# PATH 2 — CLOUD CLIENT ONLY
# ══════════════════════════════════════════════════════════════════════════════

def install_cloud():
    client_dir = INSTALL_DIR / "client"
    client_dir.mkdir(parents=True, exist_ok=True)

    # ── Python ────────────────────────────────────────────────────────────────
    step("Checking Python...")
    python = find_python()
    if not python:
        warn("Python >= 3.12 not found.")
        ans = input("Download and install Python 3.12? [Y/N]: ").strip().lower()
        if ans == "y":
            py_url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
            py_tmp = Path(os.environ["TEMP"]) / "python-3.12-installer.exe"
            info("Downloading Python 3.12...")
            download(py_url, py_tmp)
            subprocess.run([str(py_tmp), "/passive", "InstallAllUsers=0",
                            "PrependPath=1", "Include_launcher=1"], check=True)
            py_tmp.unlink(missing_ok=True)
            python = find_python()
            if not python:
                fail("Python not found after install. Re-open this installer.")
        else:
            fail("Python >= 3.12 required.")
    info(f"Python: {python}")

    # ── Agent source ──────────────────────────────────────────────────────────
    step("Setting up agent...")
    agent_py = client_dir / "agent.py"
    if not agent_py.exists():
        app_dir = client_dir / "_app"
        ensure_app_source(app_dir)
        shutil.copy(app_dir / "atomic_client" / "agent.py", agent_py)
        shutil.rmtree(app_dir, ignore_errors=True)

    # ── venv + deps ───────────────────────────────────────────────────────────
    step("Installing dependencies...")
    venv = client_dir / ".venv"
    if not venv.exists():
        run(python, "-m", "venv", str(venv))
    pip = str(venv / "Scripts" / "pip.exe")
    venv_py = str(venv / "Scripts" / "python.exe")
    run(pip, "install", "--quiet", "--upgrade", "pip")
    run(pip, "install", "--quiet",
        "websockets", "rich", "requests", "python-dotenv", "cryptography")
    info("Dependencies installed.")

    # ── API key ───────────────────────────────────────────────────────────────
    print("\nYou'll need an API key to connect (or press Enter to configure later).")
    api_key = input("API key: ").strip()

    # ── .env.client ───────────────────────────────────────────────────────────
    step("Writing .env.client...")
    env_path = client_dir / ".env.client"
    env_path.write_text(f"""\
INSTALL_MODE=cloud
AGENT_API_KEY={api_key or 'YOUR_KEY_HERE'}
ATOMIC_HOST=https://agent.eric-merritt.com
AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws
ALLOWED_PATHS={Path.home()}
""", encoding="utf-8")
    env_path.chmod(env_path.stat().st_mode & ~(stat.S_IRGRP | stat.S_IROTH))

    # ── agent.bat ─────────────────────────────────────────────────────────────
    agent_bat = client_dir / "agent.bat"
    agent_bat.write_text(
        f'@echo off\n'
        f'set "DIR={client_dir}"\n'
        f'set /p _dummy=< "%DIR%\\.env.client" 2>nul\n'
        f'for /f "usebackq tokens=1,* delims==" %%A in ("%DIR%\\.env.client") do set "%%A=%%B"\n'
        f'"%DIR%\\.venv\\Scripts\\python.exe" "%DIR%\\agent.py" %*\n',
        encoding="utf-8")

    # ── Desktop shortcut ──────────────────────────────────────────────────────
    _create_shortcut(
        name="Atomic Chat Agent",
        target=str(agent_bat),
        description="Connect to Atomic Chat cloud service",
    )

    print(f"\n{GREEN}{BOLD}══════════════════════════════════{RESET}")
    print(f"{GREEN}{BOLD}  Installation complete!{RESET}")
    print(f"{GREEN}{BOLD}══════════════════════════════════{RESET}\n")
    info("Start: double-click 'Atomic Chat Agent' on your Desktop, or run:")
    print(f"  {agent_bat}")
    if not api_key:
        warn(f"Set AGENT_API_KEY in {env_path} before running.")
    print()

# ── Desktop shortcut helper ────────────────────────────────────────────────────

def _create_shortcut(name, target, description="", icon=""):
    try:
        import winreg
        desktop = Path(subprocess.run(
            ["powershell", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True).stdout.strip())
        lnk = desktop / f"{name}.lnk"
        ps = (
            f'$ws = New-Object -ComObject WScript.Shell;'
            f'$s = $ws.CreateShortcut("{lnk}");'
            f'$s.TargetPath = "{target}";'
            f'$s.Description = "{description}";'
        )
        if icon and Path(icon).exists():
            ps += f'$s.IconLocation = "{icon}";'
        ps += '$s.Save()'
        subprocess.run(["powershell", "-Command", ps], capture_output=True)
        info(f"Shortcut created: {lnk}")
    except Exception as e:
        warn(f"Could not create desktop shortcut: {e}")

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}╔══════════════════════════════════╗{RESET}")
    print(f"{BOLD}║   Atomic Chat  —  Setup Wizard   ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════╝{RESET}\n")
    print(f"Install directory: {INSTALL_DIR}\n")
    print(f"{BOLD}Choose installation type:{RESET}")
    print("  [1] Full Local Stack    — self-hosted LLM + backend + frontend, no cloud")
    print("  [2] Cloud Client Only   — connect your machine to agent.eric-merritt.com\n")

    choice = input("Choice [1/2]: ").strip()
    if choice == "1":
        install_local()
    elif choice == "2":
        install_cloud()
    else:
        fail("Enter 1 or 2.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
